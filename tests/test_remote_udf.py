"""Tests for remote UDF module streaming (wrapper source, payload, dispatch).

Covers the design contract for streaming ``module: file.py::func`` steps to
remote hosts: wrapper rendering, local execution of the generated wrapper,
sentinel parsing/merging, cloud dispatch through the python payload path, and
session script/bundle routing.
"""

from __future__ import annotations

import base64
import json
import py_compile
import re
import subprocess
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from ofx.cloud.script_runtime import (
    build_module_step_payload,
    build_udf_step_source,
    is_udf_module_step,
    parse_module_outputs_sentinel,
)
from ofx.cloud.sessions.python_steps import iter_python_step_bundles
from ofx.cloud.sessions.script_builder import build_session_script
from ofx.models.step import Step
from ofx.runner import RunContext
from ofx.runner.cloud_step import CloudStepRunner, _RemoteHandlerRunner

_SENTINEL = "__OFX_MODULE_OUTPUTS__"

_UDF_SOURCE = """\
def run(ctx):
    total = sum(ctx.inputs.get("values", []))
    ctx.add_outputs(total=total)
    ctx.add_outputs(greeting=ctx.secrets.get("greeting", ""))
    print("running udf")
    return {"extra": "returned-dict"}
"""


def _udf_step(tmp_path: Path, source: str = _UDF_SOURCE, **kwargs) -> Step:
    udf_file = tmp_path / "my_udf.py"
    udf_file.write_text(source)
    module = kwargs.pop("module", None) or f"{udf_file}::run"
    data = {"name": "u", "module": module, "with": kwargs.pop("run_with", {}) or {}}
    data.update(kwargs)
    return Step.model_validate(data)


def _encode_outputs(outputs: dict) -> str:
    return base64.b64encode(json.dumps(outputs).encode()).decode()


def _decode_sentinel(stdout: str) -> dict:
    line = [item for item in stdout.splitlines() if item.startswith(_SENTINEL)][-1]
    return json.loads(base64.b64decode(line[len(_SENTINEL):]).decode())


class TestIsUdfModuleStep:
    def test_udf_specs(self):
        assert is_udf_module_step(Step(module="scripts/tool.py::run", run_with={}))
        assert is_udf_module_step(Step(module="scripts/tool.py", run_with={}))
        assert is_udf_module_step(Step(module="tool.py::my_func", run_with={}))

    def test_builtin_steps_are_not_udf(self):
        assert not is_udf_module_step(Step(module="python", run_with={"script": "x"}))
        assert not is_udf_module_step(
            Step(module="builtin.python", run_with={"script": "x"})
        )
        assert not is_udf_module_step(Step(module="shell", run_with={"cmd": "x"}))
        assert not is_udf_module_step(Step(module="builtin.shell", run_with={"cmd": "x"}))

    def test_non_module_steps_are_not_udf(self):
        assert not is_udf_module_step(Step(uses="other", run_with={}))


class TestBuildUdfStepSource:
    def test_wrapper_compiles_and_embeds_source_inputs_secrets(self, tmp_path):
        step = _udf_step(tmp_path)
        wrapper = build_udf_step_source(
            step,
            workflow_dir=tmp_path,
            inputs={"values": [1, 2, 3]},
            secrets={"greeting": "hi"},
        )

        assert "# ofx remote UDF wrapper (generated)" in wrapper
        assert "sys as _sys" in wrapper
        assert "def run(ctx):" in wrapper
        assert '"values": [1, 2, 3]' in wrapper
        assert '"greeting": "hi"' in wrapper

        generated = tmp_path / "wrapper_gen.py"
        generated.write_text(wrapper)
        py_compile.compile(str(generated), doraise=True)

    def test_wrapper_defaults_function_to_run(self, tmp_path):
        udf_file = tmp_path / "bare.py"
        udf_file.write_text("def run(ctx):\n    return {}\n")
        step = Step.model_validate(
            {"name": "u", "module": f"{udf_file}", "with": {}}
        )
        wrapper = build_udf_step_source(step, workflow_dir=tmp_path, inputs={}, secrets={})
        assert "_UDF_FUNCTION = 'run'" in wrapper

    def test_wrapper_missing_file_raises(self, tmp_path):
        step = Step.model_validate(
            {"name": "u", "module": "nope.py::run", "with": {}}
        )
        with pytest.raises(FileNotFoundError, match="nope.py"):
            build_udf_step_source(step, workflow_dir=tmp_path, inputs={}, secrets={})

    def test_wrapper_resolves_relative_spec_against_workflow_dir(self, tmp_path):
        (tmp_path / "rel_udf.py").write_text("def run(ctx):\n    return {}\n")
        step = Step.model_validate(
            {"name": "u", "module": "rel_udf.py::run", "with": {}}
        )
        wrapper = build_udf_step_source(step, workflow_dir=tmp_path, inputs={}, secrets={})
        assert "def run(ctx):" in wrapper


class TestWrapperLocalExecution:
    def test_wrapper_runs_udf_and_prints_sentinel(self, tmp_path):
        step = _udf_step(tmp_path)
        wrapper = build_udf_step_source(
            step,
            workflow_dir=tmp_path,
            inputs={"values": [1, 2, 3]},
            secrets={"greeting": "hi"},
        )
        proc = subprocess.run(
            [sys.executable, "-c", wrapper],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert proc.returncode == 0, proc.stderr
        assert "running udf" in proc.stdout
        assert proc.stdout.splitlines()[-1].startswith(_SENTINEL)
        assert _decode_sentinel(proc.stdout) == {
            "total": 6,
            "greeting": "hi",
            "extra": "returned-dict",
        }

    def test_wrapper_failing_udf_exits_1_with_traceback(self, tmp_path):
        step = _udf_step(
            tmp_path,
            source="def run(ctx):\n    raise RuntimeError('boom')\n",
        )
        wrapper = build_udf_step_source(step, workflow_dir=tmp_path, inputs={}, secrets={})
        proc = subprocess.run(
            [sys.executable, "-c", wrapper],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert proc.returncode == 1
        assert "RuntimeError: boom" in proc.stderr
        assert _decode_sentinel(proc.stdout) == {}

    def test_wrapper_serializes_non_json_inputs_with_default_str(self, tmp_path):
        step = _udf_step(
            tmp_path,
            source="def run(ctx):\n    ctx.add_outputs(seen=ctx.inputs.get('obj'))\n",
        )
        wrapper = build_udf_step_source(
            step,
            workflow_dir=tmp_path,
            inputs={"obj": object()},
            secrets={},
        )
        proc = subprocess.run(
            [sys.executable, "-c", wrapper],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert proc.returncode == 0, proc.stderr
        assert isinstance(_decode_sentinel(proc.stdout)["seen"], str)


class TestParseModuleOutputsSentinel:
    def test_sentinel_merged_and_stdout_cleaned(self):
        stdout = f"doing work\n{_SENTINEL}{_encode_outputs({'total': 6})}\n"
        cleaned, outputs = parse_module_outputs_sentinel(stdout)
        assert cleaned == "doing work\n"
        assert outputs == {"total": 6}

    def test_no_sentinel_keeps_raw_stdout(self):
        stdout = "plain output\n"
        cleaned, outputs = parse_module_outputs_sentinel(stdout)
        assert cleaned == stdout
        assert outputs == {}

    def test_invalid_sentinel_keeps_raw_stdout(self):
        stdout = f"x\n{_SENTINEL}not-base64!!\n"
        cleaned, outputs = parse_module_outputs_sentinel(stdout)
        assert cleaned == stdout
        assert outputs == {}

    def test_last_occurrence_wins(self):
        first = f"first\n{_SENTINEL}{_encode_outputs({'n': 1})}\n"
        stdout = first + f"last\n{_SENTINEL}{_encode_outputs({'n': 2})}\n"
        cleaned, outputs = parse_module_outputs_sentinel(stdout)
        assert outputs == {"n": 2}
        # Only the last sentinel line is stripped.
        assert cleaned == first + "last\n"


class TestBuildModuleStepPayload:
    def test_python_steps_use_existing_path(self):
        step = Step.model_validate(
            {"name": "p", "module": "python", "with": {"script": "print('hi')"}}
        )
        payload = build_module_step_payload(step, opsec_mode=False, obfuscate_sources=False)
        assert "print('hi')" in payload
        assert "ofx remote UDF wrapper" not in payload

    def test_udf_extra_modules_collected_from_embedded_source(self, tmp_path):
        udf_file = tmp_path / "api_udf.py"
        udf_file.write_text(
            "import ofx.api.opsec\n\n"
            "def run(ctx):\n"
            "    return {'used_opsec': True}\n"
        )
        step = Step.model_validate(
            {"name": "u", "module": f"{udf_file}::run", "with": {}}
        )
        payload = build_module_step_payload(
            step,
            workflow_dir=tmp_path,
            inputs={},
            secrets={},
            opsec_mode=False,
            obfuscate_sources=False,
        )
        assert "ofx remote UDF wrapper" in payload
        assert "import ofx.api.opsec" in payload  # embedded UDF source

        # The bundled zip must contain the ofx.api.opsec module files.
        match = re.search(r"_b64\.b64decode\('([^']+)'\)", payload)
        assert match, "bootstrap should embed the base64 zip archive"
        with zipfile.ZipFile(BytesIO(base64.b64decode(match.group(1)))) as zf:
            members = zf.namelist()
        assert any(name.startswith("ofx/api/opsec") for name in members)

    def test_udf_obfuscated_payload_hides_wrapper(self, tmp_path):
        step = _udf_step(tmp_path)
        payload = build_module_step_payload(
            step,
            workflow_dir=tmp_path,
            inputs={"values": [1, 2, 3]},
            secrets={"greeting": "hi"},
            opsec_mode=True,
            obfuscate_sources=True,
        )
        assert "ofx remote UDF wrapper" not in payload
        assert '"greeting": "hi"' not in payload
        assert "marshal.loads" in payload or "exec(" in payload


class TestCloudUDFDispatch:
    def _make_runner(self, step: Step, *, ctx: RunContext | None = None):
        parent_job = object.__new__(type("ParentJob", (), {}))
        parent_job._cloud_config = None
        parent_job._cached_python = "python3"
        runner = CloudStepRunner.__new__(CloudStepRunner)
        runner.model = step
        runner.ctx = ctx or RunContext(secrets={})
        runner.parent = parent_job
        runner._remote = None
        runner._work_dir = "/tmp"
        runner._log_debug = lambda msg: None
        return runner

    @pytest.mark.asyncio
    async def test_udf_step_returns_cleaned_stdout_and_parsed_outputs(
        self, tmp_path, monkeypatch
    ):
        step = _udf_step(tmp_path)
        ctx = RunContext(secrets={"greeting": "hi"}, workflow_dir=tmp_path)
        runner = self._make_runner(step, ctx=ctx)
        expected_payload = build_module_step_payload(
            step,
            workflow_dir=tmp_path,
            inputs=dict(step.run_with or {}),
            secrets={"greeting": "hi"},
        )

        seen: dict[str, str] = {}

        async def fake_run_payload(payload, *, timeout=None):
            seen["payload"] = payload
            return f"running udf\n{_SENTINEL}{_encode_outputs({'total': 3})}\n"

        monkeypatch.setattr(runner, "_run_remote_python_payload", fake_run_payload)
        cleaned, outputs = await runner._execute_remote_module(timeout_seconds=60)

        assert seen["payload"] == expected_payload
        assert cleaned == "running udf\n"
        assert outputs == {"total": 3}

    @pytest.mark.asyncio
    async def test_udf_step_uploads_payload_to_remote(self, tmp_path, monkeypatch):
        step = _udf_step(tmp_path)
        runner = self._make_runner(step, ctx=RunContext(secrets={}, workflow_dir=tmp_path))
        uploaded: list[tuple[str, str]] = []

        monkeypatch.setattr(
            "ofx.runner.cloud_step.upload_temp_content",
            lambda _remote, content, remote_path, suffix="": uploaded.append(
                (content, remote_path)
            ),
        )

        class _Remote:
            def run(self, cmd, timeout=None):
                return f"running udf\n{_SENTINEL}{_encode_outputs({'ok': 1})}\n"

        runner._remote = _Remote()

        cleaned, outputs = await runner._execute_remote_module(timeout_seconds=60)
        assert len(uploaded) == 1
        assert uploaded[0][1].endswith(".py")
        assert "ofx remote UDF wrapper" in uploaded[0][0]
        assert cleaned == "running udf\n"
        assert outputs == {"ok": 1}

    @pytest.mark.asyncio
    async def test_udf_parse_failure_keeps_raw_stdout(self, tmp_path, monkeypatch):
        step = _udf_step(tmp_path)
        runner = self._make_runner(step)

        async def fake_run_payload(payload, *, timeout=None):
            return "raw output\nno sentinel here\n"

        monkeypatch.setattr(runner, "_run_remote_python_payload", fake_run_payload)
        cleaned, outputs = await runner._execute_remote_module(timeout_seconds=60)
        assert cleaned == "raw output\nno sentinel here\n"
        assert outputs == {}


class TestRemoteHandlerRunnerMerging:
    def _outer(self, output):
        outer = SimpleNamespace(
            _run_type=None,
            model=SimpleNamespace(
                timeout=1,
                get_run_type=lambda: "module",
            ),
            outputs_registry={},
            is_success=True,
        )

        async def execute(run_type, *, timeout_seconds):
            return output

        async def reg_set(key, value):
            outer.outputs_registry[key] = value

        async def get_result():
            return SimpleNamespace(outputs=outer.outputs_registry.get("outputs", {}))

        outer._execute_remote_run_type = execute
        outer.reg_set = reg_set
        outer.get_result = get_result
        return outer

    @pytest.mark.asyncio
    async def test_udf_tuple_merges_outputs_with_cleaned_stdout(self):
        stdout = f"running udf\n{_SENTINEL}{_encode_outputs({'total': 6})}\n"
        cleaned, parsed = parse_module_outputs_sentinel(stdout)
        outer = self._outer((cleaned, parsed))
        result = await _RemoteHandlerRunner(outer).run()
        assert result.outputs == {"stdout": "running udf\n", "total": 6}

    @pytest.mark.asyncio
    async def test_str_output_keeps_existing_behavior(self):
        outer = self._outer("plain output\n")
        result = await _RemoteHandlerRunner(outer).run()
        assert result.outputs == {"stdout": "plain output\n"}


class TestSessionRouting:
    def test_bash_session_routes_udf_to_staged_python_command(self, tmp_path):
        step = _udf_step(tmp_path)
        script = build_session_script([step], session_id="s1", work_dir="/tmp/s")
        assert '"$__OFX_PY_BIN" ".ofx_step_0.py"' in script

    def test_powershell_session_routes_udf_to_staged_python_command(self, tmp_path):
        step = _udf_step(tmp_path)
        script = build_session_script(
            [step], session_id="s1", work_dir="C:\\work", os_type="windows"
        )
        assert '$__ofx_py = Join-Path $WORK_DIR ".ofx_step_0.py"' in script

    def test_shell_steps_still_use_run_with_cmd(self, tmp_path):
        udf_step = _udf_step(tmp_path)
        shell_step = Step.model_validate(
            {"name": "s", "module": "shell", "with": {"cmd": "echo hi"}}
        )
        script = build_session_script(
            [udf_step, shell_step], session_id="s1", work_dir="/tmp/s"
        )
        assert '"$__OFX_PY_BIN" ".ofx_step_0.py"' in script
        assert "echo hi" in script


class TestIterPythonStepBundles:
    def test_yields_udf_steps_with_obfuscated_payload(self, tmp_path):
        step = _udf_step(tmp_path, source='print("UDF_SECRET_MARKER")\ndef run(ctx):\n    return {"ok": 1}\n')
        idx, filename, payload = next(iter_python_step_bundles([step], workflow_dir=tmp_path))
        assert idx == 0
        assert filename == ".ofx_step_0.py"
        assert "UDF_SECRET_MARKER" not in payload
        assert "marshal.loads" in payload or "exec(" in payload

    def test_mixed_steps_stage_python_and_udf_bundles(self, tmp_path):
        py_step = Step.model_validate(
            {"name": "p", "module": "python", "with": {"script": "print('py')"}}
        )
        shell_step = Step.model_validate(
            {"name": "s", "module": "shell", "with": {"cmd": "echo hi"}}
        )
        udf_step = _udf_step(tmp_path)
        bundles = list(
            iter_python_step_bundles(
                [py_step, shell_step, udf_step], workflow_dir=tmp_path
            )
        )
        assert [(idx, name) for idx, name, _ in bundles] == [
            (0, ".ofx_step_0.py"),
            (2, ".ofx_step_2.py"),
        ]
