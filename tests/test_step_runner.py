"""Tests for step working-directory resolution helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ofx.models.step import Step
from ofx.runner import RunContext, RunnerStatus
from ofx.runner.cloud_step import CloudStepRunner
from ofx.runner.handlers.registry import registry
from ofx.runner.step import StepRunner
from ofx.models.step import RunType


def _capture_save_runner_output(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_save_output_file(
        output_path,
        job_id,
        step_model,
        stdout,
        outputs=None,
        *,
        log_fn=None,
    ):
        captured.update(
            {
                "output_path": output_path,
                "job_id": job_id,
                "step_model": step_model,
                "stdout": stdout,
                "outputs": outputs,
                "log_fn": log_fn,
            }
        )

    monkeypatch.setattr(
        "ofx.runner.step_output.save_output_file",
        _fake_save_output_file,
    )
    return captured


def _make_pre_run_step_runner(step: Step, ctx: RunContext) -> StepRunner:
    runner = object.__new__(StepRunner)
    runner.model = step
    runner.ctx = ctx
    runner.parent = None
    runner._state_machine = SimpleNamespace(transition=lambda _status: None)
    runner._apply_retry_profile_defaults = lambda: None
    runner._resolve_template_fields = AsyncMock(return_value=None)
    runner._resolve_timeout_field = AsyncMock(return_value=None)
    runner._resolve_template = AsyncMock(return_value=None)
    runner._evaluate_run_if = lambda _expr, _context=None: True
    runner._run_if_context = lambda: {}
    runner.reg_set = AsyncMock(return_value=None)
    return runner


def _make_run_if_step_runner(step_index: int = 0):
    runner = object.__new__(StepRunner)
    runner.model = Step(run="echo hi", step_index=step_index)
    runner.ctx = RunContext()
    runner.parent = SimpleNamespace(_runners={})
    return runner


def test_resolve_working_dir_uses_context_default_when_step_omits_field(tmp_path):
    runner = object.__new__(StepRunner)
    runner.model = Step(script="print('hi')")
    runner.ctx = RunContext(vars={"working_directory": tmp_path / "workspace"})

    assert runner._resolve_working_dir() == (tmp_path / "workspace")


def test_resolve_working_dir_resolves_relative_context_path(tmp_path, monkeypatch):
    runner = object.__new__(StepRunner)
    runner.model = Step(script="print('hi')")
    monkeypatch.chdir(tmp_path)
    runner.ctx = RunContext(vars={"working_directory": Path("nested")})

    assert runner._resolve_working_dir() == (tmp_path / "nested").resolve()


def test_resolve_working_dir_resolves_relative_step_path_against_context(tmp_path):
    runner = object.__new__(StepRunner)
    runner.model = Step(script="print('hi')", **{"working-directory": "nested"})
    runner.ctx = RunContext(vars={"working_directory": tmp_path / "workspace"})

    assert runner._resolve_working_dir() == (tmp_path / "workspace" / "nested").resolve()


def test_resolve_remote_work_dir_ignores_default_local_working_directory():
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(script="print('hi')")
    runner.parent = SimpleNamespace(model=SimpleNamespace(defaults=SimpleNamespace(run=None)))
    runner._work_dir = "/tmp/ofx-run"

    assert runner._resolve_remote_work_dir() == "/tmp/ofx-run"


def test_resolve_remote_work_dir_honors_explicit_step_working_directory():
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(script="print('hi')", **{"working-directory": "/opt/custom"})
    runner.parent = SimpleNamespace(model=SimpleNamespace(defaults=SimpleNamespace(run=None)))
    runner._work_dir = "/tmp/ofx-run"

    assert runner._resolve_remote_work_dir() == "/opt/custom"


def test_script_handler_uses_resolved_working_directory(tmp_path):
    step_runner = SimpleNamespace(
        model=Step(script="print('hi')"),
        ctx=RunContext(
            vars={"working_directory": tmp_path / "workspace"},
            workflow_dir=tmp_path,
        ),
        parent=None,
        _child_context=lambda update=None: RunContext(),
        _resolve_working_dir=lambda: (tmp_path / "workspace").resolve(),
        _resolve_shell=lambda: "/bin/sh",
    )

    runner = registry.get(RunType.SCRIPT)(step_runner)

    assert runner.model.working_directory == (tmp_path / "workspace").resolve()


def test_script_file_handler_uses_resolved_working_directory(tmp_path):
    script_path = tmp_path / "worker.py"
    script_path.write_text("print('hi')\n")
    step_runner = SimpleNamespace(
        model=Step(script_file="worker", **{"working-directory": "nested"}),
        ctx=RunContext(workflow_dir=tmp_path),
        parent=None,
        _child_context=lambda update=None: RunContext(),
        _resolve_working_dir=lambda: (tmp_path / "workspace" / "nested").resolve(),
        _resolve_shell=lambda: "/bin/sh",
    )

    runner = registry.get(RunType.SCRIPT_FILE)(step_runner)

    assert runner.model.working_directory == (tmp_path / "workspace" / "nested").resolve()


def test_command_handler_uses_resolved_shell():
    step_runner = SimpleNamespace(
        model=Step(run="echo hi"),
        ctx=RunContext(),
        parent=SimpleNamespace(
            model=SimpleNamespace(
                defaults=SimpleNamespace(run=SimpleNamespace(shell="/bin/sh"))
            )
        ),
        _child_context=lambda update=None: RunContext(),
        _resolve_working_dir=lambda: Path.cwd(),
    )

    runner = registry.get(RunType.COMMAND)(step_runner)

    assert runner.model.shell == "/bin/sh"


def test_command_handler_honors_explicit_step_shell():
    step_runner = SimpleNamespace(
        model=Step(run="echo hi", shell="/bin/zsh"),
        ctx=RunContext(),
        parent=SimpleNamespace(
            model=SimpleNamespace(
                defaults=SimpleNamespace(run=SimpleNamespace(shell="/bin/sh"))
            )
        ),
        _child_context=lambda update=None: RunContext(),
        _resolve_working_dir=lambda: Path.cwd(),
    )

    runner = registry.get(RunType.COMMAND)(step_runner)

    assert runner.model.shell == "/bin/zsh"


def test_task_handler_uses_resolved_shell():
    store_creds_calls: list[tuple[object, object]] = []
    step_runner = SimpleNamespace(
        model=Step(task="httpx", run_with={"target": "example.com"}),
        ctx=RunContext(),
        parent=SimpleNamespace(
            model=SimpleNamespace(
                defaults=SimpleNamespace(run=SimpleNamespace(shell="/bin/sh"))
            )
        ),
        _child_context=lambda update=None: RunContext(),
        _resolve_working_dir=lambda: Path.cwd(),
        _log_warning=lambda _message: None,
    )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "ofx.runner.services.credential_store.should_store_creds",
            lambda step_store_creds, parent_model: store_creds_calls.append((step_store_creds, parent_model)) or False,
        )
        runner = registry.get(RunType.TASK)(step_runner)

    assert runner.model.shell == "/bin/sh"
    assert store_creds_calls == [(None, step_runner.parent.model)]


def test_task_handler_joins_target_list():
    step_runner = SimpleNamespace(
        model=Step(task="httpx", run_with={"targets": ["a", "b"], "threads": 2}),
        ctx=RunContext(),
        parent=None,
        _child_context=lambda update=None: RunContext(),
        _resolve_working_dir=lambda: Path.cwd(),
        _log_warning=lambda _message: None,
    )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "ofx.runner.services.credential_store.should_store_creds",
            lambda step_store_creds, parent_model: False,
        )
        runner = registry.get(RunType.TASK)(step_runner)

    assert runner.model.target == "a,b"
    assert runner.model.opts == {"threads": 2}


def test_script_handler_uses_resolved_shell():
    step_runner = SimpleNamespace(
        model=Step(script="print('hi')"),
        ctx=RunContext(workflow_dir=Path.cwd()),
        parent=SimpleNamespace(
            model=SimpleNamespace(
                defaults=SimpleNamespace(run=SimpleNamespace(shell="/bin/sh"))
            )
        ),
        _child_context=lambda update=None: RunContext(),
        _resolve_working_dir=lambda: Path.cwd(),
    )

    runner = registry.get(RunType.SCRIPT)(step_runner)

    assert runner.model.shell == "/bin/sh"
def test_run_if_context_defaults_when_no_previous_step_runner():
    runner = _make_run_if_step_runner(step_index=0)

    ctx = runner._run_if_context()

    assert ctx["success"]() is True
    assert ctx["failure"]() is False
    assert ctx["canceled"]() is False
    assert ctx["always"]() is True


def test_run_if_context_uses_previous_step_runner_status():
    runner = _make_run_if_step_runner(step_index=2)
    runner.parent._runners["1"] = SimpleNamespace(
        is_success=False,
        is_failed=True,
        status=RunnerStatus.FAILED,
    )

    ctx = runner._run_if_context()

    assert ctx["success"]() is False
    assert ctx["failure"]() is True


def test_ensure_run_if_condition_cancels_when_expression_is_false():
    runner = _make_run_if_step_runner(step_index=1)
    transitions: list[RunnerStatus] = []
    runner._state_machine = SimpleNamespace(transition=lambda status: transitions.append(status))
    runner._evaluate_run_if = lambda _expr, _context=None: False

    with pytest.raises(Exception, match="Step skipped"):
        runner._ensure_run_if_condition("Step skipped")

    assert transitions == [RunnerStatus.CANCELED]

def test_previous_step_runners_wraps_previous_runner_when_present():
    runner = _make_run_if_step_runner(step_index=2)
    previous = SimpleNamespace(
        status=RunnerStatus.COMPLETED,
        is_success=True,
        is_failed=False,
    )
    runner.parent._runners["1"] = previous

    ctx = runner._run_if_context()

    assert ctx["success"]() is True
    assert ctx["failure"]() is False


def test_previous_step_lookup_helpers_handle_missing_parent_and_first_step():
    runner = _make_run_if_step_runner(step_index=0)
    runner.parent = None

    ctx = runner._run_if_context()
    assert ctx["success"]() is True
    assert ctx["failure"]() is False

def test_format_typed_outputs_renders_when_payload_present(monkeypatch):
    runner = _make_run_if_step_runner(step_index=1)
    rendered: list[tuple[list[dict[str, str]], str, object]] = []
    result = SimpleNamespace(outputs={"typed_outputs": [{"_type": "ip", "ip": "1.1.1.1"}]})

    def _capture_render(typed_outputs, *, task_name, console):
        rendered.append((list(typed_outputs), task_name, console))

    monkeypatch.setattr("ofx.runner.output_formatter.format_typed_outputs", _capture_render)
    monkeypatch.setattr("ofx.settings.get_console", lambda: "console")
    runner.model.name = "scan-step"

    assert runner._format_typed_outputs(result) is True

    assert rendered == [([{"_type": "ip", "ip": "1.1.1.1"}], "scan-step", "console")]


def test_emit_result_outputs_logs_streams_and_saves_stdout(tmp_path):
    runner = _make_run_if_step_runner(step_index=1)
    runner.ctx = RunContext(output_path=tmp_path)
    runner.model = Step(run="echo hi", **{"log-stdout": True})
    logs: list[tuple[str, str]] = []
    saves: list[tuple[str, dict[str, str]]] = []
    runner._format_typed_outputs = lambda _result: False
    runner._save_runner_output = lambda stdout, outputs, **kwargs: saves.append(
        (stdout, dict(outputs), dict(kwargs))
    )
    result = SimpleNamespace(outputs={"stdout": "ok", "stderr": "warn"})

    def _capture_log_output(log_fn, stream, content):
        logs.append((stream, content))

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("ofx.runner.step_output.log_output", _capture_log_output)

    try:
        runner._emit_result_outputs(result)
    finally:
        monkeypatch.undo()

    assert logs == [("stdout", "ok"), ("stderr", "warn")]
    assert saves == [
        (
            "ok",
            {"stdout": "ok", "stderr": "warn"},
            {
                "missing_output_path_message": "No output_path configured, skipping log file save.",
                "warn_on_missing_output_path": True,
            },
        )
    ]


@pytest.mark.asyncio
async def test_pre_run_injects_runner_and_ofx_outputs_for_command_steps():
    runner = _make_pre_run_step_runner(Step(run="echo hi"), RunContext())

    await runner._pre_run()

    assert runner._outputs_file is not None
    assert runner.ctx.envs["RUNNER_OUTPUTS"] == str(runner._outputs_file)
    assert runner.ctx.envs["OFX_OUTPUTS"] == str(runner._outputs_file)
    runner._outputs_file.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_pre_run_skips_outputs_file_for_interactive_command_steps():
    runner = _make_pre_run_step_runner(
        Step(run="echo hi", interactive=True),
        RunContext(),
    )

    await runner._pre_run()

    assert runner._outputs_file is None
    assert "RUNNER_OUTPUTS" not in runner.ctx.envs
    assert "OFX_OUTPUTS" not in runner.ctx.envs

def test_cloud_save_output_uses_shared_runner_output_helper(monkeypatch, tmp_path):
    captured = _capture_save_runner_output(monkeypatch)
    runner = object.__new__(CloudStepRunner)
    runner.ctx = RunContext(output_path=tmp_path)
    runner.parent = SimpleNamespace(model=SimpleNamespace(jid="job-1"))
    runner.model = Step(run="echo hi")
    runner._log_info = lambda _message: None
    runner._log_warning = lambda _message: None

    runner._save_runner_output("stdout")

    assert captured["output_path"] == tmp_path
    assert captured["job_id"] == "job-1"
    assert captured["stdout"] == "stdout"
    assert captured["outputs"] is None
    assert callable(captured["log_fn"])


def test_save_runner_output_warns_when_output_path_missing():
    runner = object.__new__(CloudStepRunner)
    warnings: list[str] = []
    runner.ctx = RunContext(output_path=None)
    runner.parent = SimpleNamespace(model=SimpleNamespace(jid="job-1"))
    runner.model = Step(run="echo hi")
    runner._log_info = lambda _message: None
    runner._log_warning = warnings.append

    runner._save_runner_output(
        "stdout",
        missing_output_path_message="missing output path",
        warn_on_missing_output_path=True,
    )

    assert warnings == ["missing output path"]


def test_save_runner_output_skips_missing_job_id(monkeypatch, tmp_path):
    called = False

    def _unexpected(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("ofx.runner.step_output.save_output_file", _unexpected)
    runner = object.__new__(CloudStepRunner)
    runner.ctx = RunContext(output_path=tmp_path)
    runner.parent = None
    runner.model = Step(run="echo hi")
    runner._log_info = lambda _message: None
    runner._log_warning = lambda _message: None

    runner._save_runner_output("stdout")

    assert called is False
