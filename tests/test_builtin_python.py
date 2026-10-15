"""Tests for the builtin ``python`` module (single code path for python steps).

Covers the features folded in from the removed ``ScriptRunner``/
``exec_script_in_process``: scope-model injection (``__job__``/``__step__``/
``__workflow__``), ``$RUNNER_OUTPUTS`` file writes, channel store
primitives, ``export_typed_outputs`` availability, and ``ctx.env``
export/restore around script execution.
"""

from __future__ import annotations

import json
import os

import pytest

from ofx.modules import ModuleInvocation, ModuleRunner
from ofx.modules.base import ModuleContext
from ofx.modules.builtins import python as python_module
from ofx.runner import RunContext, RunnerStatus
from ofx.runner.channels import ChannelStore
from ofx.runner.registry_keys import RunnerRegistryKeys


def _ctx(
    args: dict | None = None,
    *,
    env: dict | None = None,
    scope_models=None,
    channels_dir: str | None = None,
    publish=None,
    subscribe=None,
    wait_for=None,
    add_outputs=None,
) -> ModuleContext:
    return ModuleContext(
        args=dict(args or {}),
        env=dict(env or {}),
        scope_models=scope_models,
        channels_dir=channels_dir,
        publish=publish,
        subscribe=subscribe,
        wait_for=wait_for,
        add_outputs=add_outputs,
    )


class TestPythonBasic:
    def test_executes_script_and_captures_stdout(self):
        result = python_module.run(_ctx({"script": "print('python-ok')"}))
        assert result.exit_code == 0
        assert result.stdout.strip() == "python-ok"

    def test_runtime_error_fails_with_traceback(self):
        result = python_module.run(_ctx({"script": "raise ValueError('boom')"}))
        assert result.exit_code == 1
        assert "Traceback" in result.stderr
        assert "boom" in result.stderr

    def test_syntax_error_fails(self):
        result = python_module.run(_ctx({"script": "this is not valid python!!!"}))
        assert result.exit_code == 1
        assert "Traceback" in result.stderr

    def test_large_script_runs(self):
        large = "# " + ("x" * 3000) + "\nprint('large executed')"
        result = python_module.run(_ctx({"script": large}))
        assert result.exit_code == 0
        assert "large executed" in result.stdout

    def test_missing_script_returns_error(self):
        result = python_module.run(_ctx({}))
        assert result.exit_code == 1
        assert "requires 'script' or 'script_file'" in result.stderr

    def test_script_file_reading(self, tmp_path):
        script_file = tmp_path / "runme.py"
        script_file.write_text("print('from-file')\n")
        result = python_module.run(
            _ctx({"script_file": str(script_file)})
        )
        assert result.exit_code == 0
        assert "from-file" in result.stdout

    def test_missing_script_file_reports_error(self, tmp_path):
        result = python_module.run(
            _ctx({"script_file": str(tmp_path / "nope.py")})
        )
        assert result.exit_code == 1
        assert "Failed to read script file" in result.stderr


class TestPythonScopeModels:
    def test_scope_models_injected(self):
        workflow = object()
        job = object()
        step = object()
        result = python_module.run(
            _ctx(
                {
                    "script": (
                        "print(__workflow__ is not None, "
                        "__job__ is not None, __step__ is not None)\n"
                    ),
                },
                scope_models=(workflow, job, step),
            )
        )
        assert result.exit_code == 0
        assert result.stdout.strip() == "True True True"

    def test_scope_models_none_when_unset(self):
        result = python_module.run(
            _ctx({"script": "print(__workflow__, __job__, __step__)"})
        )
        assert result.exit_code == 0
        assert result.stdout.strip() == "None None None"

    def test_scope_models_order(self):
        """(workflow, job, step) ordering matches the ModuleContext contract."""
        result = python_module.run(
            _ctx(
                {"script": "print(__workflow__, __job__, __step__)"},
                scope_models=("WF", "JOB", "STEP"),
            )
        )
        assert result.stdout.strip() == "WF JOB STEP"


class TestPythonOutputsFile:
    def test_add_outputs_writes_file_and_in_memory(self, tmp_path):
        outputs_file = tmp_path / "outputs.txt"
        result = python_module.run(
            _ctx(
                {"script": "add_outputs(name='Alice', age=30)"},
                env={"RUNNER_OUTPUTS": str(outputs_file)},
            )
        )
        assert result.exit_code == 0
        assert result.outputs["name"] == "Alice"
        assert result.outputs["age"] == "30"
        lines = outputs_file.read_text().strip().splitlines()
        assert "name=Alice" in lines
        assert "age=30" in lines

    def test_dict_serialized_as_json(self, tmp_path):
        outputs_file = tmp_path / "outputs.txt"
        data = {"host": "10.0.0.1", "open": True}
        result = python_module.run(
            _ctx(
                {"script": f"add_outputs(metadata={data!r})"},
                env={"RUNNER_OUTPUTS": str(outputs_file)},
            )
        )
        assert result.exit_code == 0
        assert json.loads(result.outputs["metadata"]) == data
        line = outputs_file.read_text().strip()
        parsed = json.loads(line.split("=", 1)[1])
        assert parsed == data

    def test_list_serialized_as_json(self, tmp_path):
        outputs_file = tmp_path / "outputs.txt"
        items = ["a", "b", "c"]
        result = python_module.run(
            _ctx(
                {"script": f"add_outputs(hosts={items!r})"},
                env={"RUNNER_OUTPUTS": str(outputs_file)},
            )
        )
        assert result.exit_code == 0
        assert json.loads(result.outputs["hosts"]) == items
        line = outputs_file.read_text().strip()
        assert json.loads(line.split("=", 1)[1]) == items

    def test_boolean_and_none_values(self, tmp_path):
        outputs_file = tmp_path / "outputs.txt"
        result = python_module.run(
            _ctx(
                {"script": "add_outputs(success=True, failed=False, result=None)"},
                env={"RUNNER_OUTPUTS": str(outputs_file)},
            )
        )
        assert result.exit_code == 0
        assert result.outputs["success"] == "True"
        assert result.outputs["failed"] == "False"
        assert result.outputs["result"] == "None"
        lines = outputs_file.read_text().strip().splitlines()
        assert "success=True" in lines
        assert "failed=False" in lines
        assert "result=None" in lines

    def test_multiple_calls_append(self, tmp_path):
        outputs_file = tmp_path / "outputs.txt"
        result = python_module.run(
            _ctx(
                {
                    "script": (
                        'add_outputs(a="1")\nadd_outputs(b="2")\n'
                    )
                },
                env={"RUNNER_OUTPUTS": str(outputs_file)},
            )
        )
        assert result.exit_code == 0
        assert result.outputs == {"a": "1", "b": "2"}
        assert outputs_file.read_text().strip().splitlines() == ["a=1", "b=2"]

    def test_kwargs_expansion(self, tmp_path):
        outputs_file = tmp_path / "outputs.txt"
        result = python_module.run(
            _ctx(
                {
                    "script": (
                        'results = {"host": "10.0.0.1", "port": "22"}\n'
                        "add_outputs(**results)\n"
                    )
                },
                env={"RUNNER_OUTPUTS": str(outputs_file)},
            )
        )
        assert result.exit_code == 0
        assert result.outputs["host"] == "10.0.0.1"
        assert result.outputs["port"] == "22"
        lines = outputs_file.read_text().strip().splitlines()
        assert "host=10.0.0.1" in lines
        assert "port=22" in lines

    def test_no_outputs_file_is_noop(self):
        result = python_module.run(_ctx({"script": "add_outputs(k='v')"}))
        assert result.exit_code == 0
        assert result.outputs["k"] == "v"


class TestPythonChannels:
    def test_publish_subscribe_primitives(self, tmp_path):
        store = ChannelStore(tmp_path)
        script = (
            "publish('str_chan', 'hello world')\n"
            "val = next(subscribe('str_chan'))\n"
            "print(f'Got: {val}')\n"
        )
        result = python_module.run(
            _ctx(
                {"script": script},
                channels_dir=str(tmp_path),
                publish=store.publish,
                subscribe=store.subscribe,
                wait_for=store.wait_for,
            )
        )
        assert result.exit_code == 0
        assert "Got: hello world" in result.stdout

    def test_publish_subscribe_dict_and_list(self, tmp_path):
        store = ChannelStore(tmp_path)
        script = (
            "publish('dict_chan', {'key': 'value'})\n"
            "d = next(subscribe('dict_chan'))\n"
            "print(f'Got: {d}')\n"
            "publish('list_chan', [1, 2, 3])\n"
            "l = next(subscribe('list_chan'))\n"
            "print(f'Got: {l}')\n"
        )
        result = python_module.run(
            _ctx(
                {"script": script},
                channels_dir=str(tmp_path),
                publish=store.publish,
                subscribe=store.subscribe,
                wait_for=store.wait_for,
            )
        )
        assert result.exit_code == 0
        assert "Got: {'key': 'value'}" in result.stdout
        assert "Got: [1, 2, 3]" in result.stdout


class TestPythonGlobals:
    def test_export_typed_outputs_available(self):
        result = python_module.run(
            _ctx({"script": "print(callable(export_typed_outputs))"})
        )
        assert result.exit_code == 0
        assert result.stdout.strip() == "True"

    def test_inputs_secrets_ctx_available(self):
        ctx = ModuleContext(
            args={
                "script": (
                    "print(__inputs__.get('target'), __secrets__.get('KEY'), "
                    "hasattr(__ctx__, 'inputs'))"
                )
            },
            inputs={"target": "example.com"},
            secrets={"KEY": "val"},
        )
        result = python_module.run(ctx)
        assert result.stdout.strip() == "example.com val True"


class TestPythonEnvVars:
    def test_ctx_env_exported_during_execution_and_restored(self):
        os.environ["MARKER_KEEP"] = "before"
        ctx = ModuleContext(
            args={"script": "import os; print(os.environ.get('PY_ONLY_VAR', 'missing'))"},
            env={"PY_ONLY_VAR": "set-here"},
        )
        result = python_module.run(ctx)
        assert result.exit_code == 0
        assert result.stdout.strip() == "set-here"
        # Restored after execution.
        assert "PY_ONLY_VAR" not in os.environ
        assert os.environ["MARKER_KEEP"] == "before"

    def test_existing_env_value_restored(self):
        os.environ["PY_OVERWRITE"] = "original"
        try:
            ctx = ModuleContext(
                args={"script": "import os; print(os.environ['PY_OVERWRITE'])"},
                env={"PY_OVERWRITE": "temporary"},
            )
            result = python_module.run(ctx)
            assert result.stdout.strip() == "temporary"
        finally:
            assert os.environ["PY_OVERWRITE"] == "original"
            os.environ.pop("PY_OVERWRITE", None)


class TestPythonViaModuleRunner:
    @pytest.mark.asyncio
    async def test_python_builtin_add_outputs_lands_in_outputs(self, tmp_path):
        outputs_file = tmp_path / "runner_outputs.txt"
        ctx = RunContext(envs={"RUNNER_OUTPUTS": str(outputs_file)})
        invocation = ModuleInvocation(
            name="python",
            args={"script": "add_outputs(greeting='hi')\nprint('py-ok')\n"},
        )
        runner = ModuleRunner(invocation, ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["greeting"] == "hi"
        assert outputs["stdout"].strip() == "py-ok"

    @pytest.mark.asyncio
    async def test_python_builtin_requires_script(self):
        runner = ModuleRunner(ModuleInvocation(name="python", args={}), RunContext())
        result = await runner.run()
        assert result.status == RunnerStatus.FAILED
        assert "requires 'script' or 'script_file'" in result.error

    @pytest.mark.asyncio
    async def test_scope_models_from_parent_chain(self, tmp_path):
        workflow = type(
            "W",
            (),
            {
                "model": "WF",
                "parent": None,
                "_namespace": lambda self: "wf",
                "__repr__": lambda self: "WF",
            },
        )()
        job = type(
            "J",
            (),
            {"model": "JOB", "parent": workflow, "_namespace": lambda self: "job"},
        )()
        step = type(
            "S",
            (),
            {
                "model": "STEP",
                "parent": job,
                "ctx": RunContext(output_path=tmp_path),
                "_namespace": lambda self: "step",
            },
        )()
        runner = ModuleRunner(
            ModuleInvocation(
                name="python",
                args={"script": "print(__workflow__, __job__, __step__)"},
            ),
            RunContext(output_path=tmp_path),
            parent=step,
        )
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["stdout"].strip() == "WF JOB STEP"


def test_write_outputs_file_helper():
    """write_outputs_file keeps the legacy key=value serialization contract."""
    import tempfile

    from ofx.modules.builtins.python import write_outputs_file

    with tempfile.NamedTemporaryFile(delete=False, mode="w") as handle:
        path = handle.name
    try:
        write_outputs_file(path, name="Alice", age=30)
        lines = open(path).read().strip().splitlines()
        assert lines == ["name=Alice", "age=30"]
        write_outputs_file(None, key="val")  # no-op
    finally:
        os.unlink(path)
