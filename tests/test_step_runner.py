"""Tests for step working-directory resolution helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ofx.models.step import Step
from ofx.runner import RunContext
from ofx.runner.cloud_step import CloudStepRunner
from ofx.runner.handlers.command import _create_command_runner
from ofx.runner.handlers.script import _create_script_file_runner, _create_script_runner
from ofx.runner.handlers.task import _create_task_runner
from ofx.runner.step import StepRunner


def _capture_save_runner_output(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_save_runner_output_file(
        output_path,
        job_id,
        step_model,
        stdout,
        outputs=None,
        *,
        log_fn=None,
        missing_output_path_message=None,
        warn_fn=None,
    ):
        captured.update(
            {
                "output_path": output_path,
                "job_id": job_id,
                "step_model": step_model,
                "stdout": stdout,
                "outputs": outputs,
                "log_fn": log_fn,
                "missing_output_path_message": missing_output_path_message,
                "warn_fn": warn_fn,
            }
        )

    monkeypatch.setattr(
        "ofx.runner.step_output.save_runner_output_file",
        _fake_save_runner_output_file,
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


def test_resolve_working_dir_uses_context_default_when_step_omits_field(tmp_path):
    runner = object.__new__(StepRunner)
    runner.model = Step(script="print('hi')")
    runner.ctx = RunContext(vars={"working_directory": tmp_path / "workspace"})

    assert runner._resolve_working_dir() == (tmp_path / "workspace")


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

    runner = _create_script_runner(step_runner)

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

    runner = _create_script_file_runner(step_runner)

    assert runner.model.working_directory == (tmp_path / "workspace" / "nested").resolve()


def test_resolve_shell_uses_job_defaults_when_step_omits_shell():
    runner = object.__new__(StepRunner)
    runner.model = Step(run="echo hi")
    runner.parent = SimpleNamespace(
        model=SimpleNamespace(
            defaults=SimpleNamespace(run=SimpleNamespace(shell="/bin/sh"))
        )
    )

    assert runner._resolve_shell() == "/bin/sh"


def test_resolve_shell_honors_explicit_step_shell():
    runner = object.__new__(StepRunner)
    runner.model = Step(run="echo hi", shell="/bin/zsh")
    runner.parent = SimpleNamespace(
        model=SimpleNamespace(
            defaults=SimpleNamespace(run=SimpleNamespace(shell="/bin/sh"))
        )
    )

    assert runner._resolve_shell() == "/bin/zsh"


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
        _resolve_shell=lambda: "/bin/sh",
    )

    runner = _create_command_runner(step_runner)

    assert runner.model.shell == "/bin/sh"


def test_task_handler_uses_resolved_shell():
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
        _resolve_shell=lambda: "/bin/sh",
        _resolve_store_creds=lambda: False,
        _log_warning=lambda _message: None,
    )

    runner = _create_task_runner(step_runner)

    assert runner.model.shell == "/bin/sh"


def test_task_handler_joins_target_list():
    step_runner = SimpleNamespace(
        model=Step(task="httpx", run_with={"targets": ["a", "b"], "threads": 2}),
        ctx=RunContext(),
        parent=None,
        _child_context=lambda update=None: RunContext(),
        _resolve_working_dir=lambda: Path.cwd(),
        _resolve_shell=lambda: "/bin/sh",
        _resolve_store_creds=lambda: False,
        _log_warning=lambda _message: None,
    )

    runner = _create_task_runner(step_runner)

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
        _resolve_shell=lambda: "/bin/sh",
    )

    runner = _create_script_runner(step_runner)

    assert runner.model.shell == "/bin/sh"


def test_script_handler_alias_reuses_same_factory():
    assert _create_script_file_runner is _create_script_runner


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


def test_save_output_file_uses_shared_runner_output_helper(monkeypatch, tmp_path):
    captured = _capture_save_runner_output(monkeypatch)
    runner = object.__new__(StepRunner)
    runner.ctx = RunContext(output_path=tmp_path)
    runner.parent = SimpleNamespace(model=SimpleNamespace(jid="job-1"))
    runner.model = Step(run="echo hi")
    runner._log_info = lambda _message: None
    runner._log_warning = lambda _message: None

    runner._save_output_file("stdout", {"x": 1})

    assert captured["output_path"] == tmp_path
    assert captured["job_id"] == "job-1"
    assert captured["stdout"] == "stdout"
    assert captured["outputs"] == {"x": 1}
    assert captured["missing_output_path_message"] == (
        "No output_path configured, skipping log file save."
    )
    assert captured["warn_fn"] is runner._log_warning


def test_cloud_save_output_uses_shared_runner_output_helper(monkeypatch, tmp_path):
    captured = _capture_save_runner_output(monkeypatch)
    runner = object.__new__(CloudStepRunner)
    runner.ctx = RunContext(output_path=tmp_path)
    runner.parent = SimpleNamespace(model=SimpleNamespace(jid="job-1"))
    runner.model = Step(run="echo hi")
    runner._log_info = lambda _message: None
    runner._log_warning = lambda _message: None

    runner._save_output("stdout")

    assert captured["output_path"] == tmp_path
    assert captured["job_id"] == "job-1"
    assert captured["stdout"] == "stdout"
    assert captured["outputs"] is None
    assert captured["missing_output_path_message"] is None
    assert captured["warn_fn"] is None
