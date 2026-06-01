from __future__ import annotations

from types import SimpleNamespace

import pytest
import yaml

from ofx.models.workflow import Workflow
from ofx.runner import RunContext, RunnerStatus
from ofx.runner.execution_results import (
    build_step_execution_result_for_runner,
    build_job_execution_result,
    build_run_if_context,
)
from ofx.runner.workflow import WorkflowRunner


class _RunType:
    def __init__(self, value: str) -> None:
        self.value = value


@pytest.mark.asyncio
async def test_job_and_step_execution_results():
    workflow_yaml = """
name: Exec Results
jobs:
  test_job:
    steps:
      - run: echo "ok"
      - run: echo "ok2"
"""
    workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
    runner = WorkflowRunner(workflow, RunContext())
    result = await runner.run()

    assert result.status == RunnerStatus.COMPLETED
    job_runner = runner.runners["test_job"]

    job_exec = await job_runner.reg_get("execution")
    assert job_exec is not None
    assert job_exec["jid"] == "test_job"
    assert job_exec["total_steps"] == 2
    assert job_exec["failed_steps"] == []
    assert len(job_exec["steps"]) == 2

    step0 = job_runner._runners["0"]
    step_exec = await step0.reg_get("execution")
    assert step_exec is not None
    assert step_exec["step_index"] == 0
    assert step_exec["status"] == RunnerStatus.COMPLETED.value


def test_build_job_execution_result_skips_runners_without_step_model():
    runner = SimpleNamespace(
        model=SimpleNamespace(jid="job-1", name="Job", steps=[1, 2]),
        status=RunnerStatus.FINISHED,
        _error=None,
        duration_ms=lambda: 500,
    )
    step_runner = SimpleNamespace(
        model=SimpleNamespace(step_index=1, name="step-1", get_run_type=lambda: _RunType("command")),
        _run_type=None,
        status=RunnerStatus.FAILED,
        _error="boom",
        duration_ms=lambda: 100,
    )
    ignored_runner = SimpleNamespace(status=RunnerStatus.COMPLETED)

    result = build_job_execution_result(
        runner,
        {"1": step_runner, "x": ignored_runner},
    )

    assert result.status == RunnerStatus.COMPLETED.value
    assert result.failed_steps == [1]
    assert result.steps == [
        {
            "step_index": 1,
            "name": "step-1",
            "run_type": "command",
            "status": RunnerStatus.FAILED.value,
            "error": "boom",
            "outputs": {},
            "duration_ms": 100,
        }
    ]


def test_build_job_execution_result_prefers_cached_run_type():
    runner = SimpleNamespace(
        model=SimpleNamespace(jid="job-1", name="Job", steps=[1]),
        status=RunnerStatus.COMPLETED,
        _error=None,
        duration_ms=lambda: 500,
    )
    step_runner = SimpleNamespace(
        model=SimpleNamespace(step_index=0, name="step-0", get_run_type=lambda: _RunType("command")),
        _run_type=_RunType("task"),
        status=RunnerStatus.FINISHED,
        _error=None,
        duration_ms=lambda: 100,
    )

    result = build_job_execution_result(runner, {"0": step_runner})

    assert result.steps[0]["run_type"] == "task"
    assert result.steps[0]["status"] == RunnerStatus.COMPLETED.value


def test_build_run_if_context_reflects_dependency_states():
    deps = [
        SimpleNamespace(is_success=True, is_failed=False, status=RunnerStatus.COMPLETED),
        SimpleNamespace(is_success=False, is_failed=True, status=RunnerStatus.FAILED),
        SimpleNamespace(is_success=False, is_failed=False, status=RunnerStatus.CANCELED),
    ]

    ctx = build_run_if_context(deps)

    assert ctx["success"]() is False
    assert ctx["failure"]() is True
    assert ctx["canceled"]() is True
    assert ctx["always"]() is True


def test_build_job_execution_result_builds_serializable_step_results():
    runner = SimpleNamespace(
        model=SimpleNamespace(jid="job-1", name="Job", steps=[1]),
        status=RunnerStatus.FINISHED,
        _error=None,
        duration_ms=lambda: 500,
    )
    step_runner = SimpleNamespace(
        model=SimpleNamespace(
            step_index=3,
            name="step-3",
            get_run_type=lambda: _RunType("command"),
        ),
        _run_type=None,
        status=RunnerStatus.FINISHED,
        _error=None,
        duration_ms=lambda: 42,
    )

    result = build_job_execution_result(runner, {"3": step_runner})

    assert result.steps == [
        {
            "step_index": 3,
            "name": "step-3",
            "run_type": "command",
            "status": RunnerStatus.COMPLETED.value,
            "error": None,
            "outputs": {},
            "duration_ms": 42,
        }
    ]


def test_build_step_execution_result_for_runner_uses_runner_metadata_and_outputs():
    step_runner = SimpleNamespace(
        model=SimpleNamespace(
            step_index=4,
            name="step-4",
            get_run_type=lambda: _RunType("script"),
        ),
        _run_type=_RunType("task"),
        duration_ms=lambda: 84,
    )

    result = build_step_execution_result_for_runner(
        step_runner,
        status=RunnerStatus.FAILED.value,
        error="boom",
        outputs={"stdout": "nope"},
    )

    assert result.to_dict() == {
        "step_index": 4,
        "name": "step-4",
        "run_type": "task",
        "status": RunnerStatus.FAILED.value,
        "error": "boom",
        "outputs": {"stdout": "nope"},
        "duration_ms": 84,
    }


def test_build_job_execution_result_skips_invalid_runners_and_tracks_failed_indexes():
    runner = SimpleNamespace(
        model=SimpleNamespace(jid="job-1", name="Job", steps=[1, 2, 3]),
        status=RunnerStatus.FINISHED,
        _error=None,
        duration_ms=lambda: 500,
    )
    valid_failed = SimpleNamespace(
        model=SimpleNamespace(step_index=2, name="step-2", get_run_type=lambda: _RunType("command")),
        _run_type=None,
        status=RunnerStatus.FAILED,
        _error="boom",
        duration_ms=lambda: 10,
    )
    valid_ok = SimpleNamespace(
        model=SimpleNamespace(step_index=3, name="step-3", get_run_type=lambda: _RunType("script")),
        _run_type=None,
        status=RunnerStatus.COMPLETED,
        _error=None,
        duration_ms=lambda: 20,
    )
    invalid = SimpleNamespace(status=RunnerStatus.FAILED)

    result = build_job_execution_result(
        runner,
        {"2": valid_failed, "x": invalid, "3": valid_ok},
    )

    assert [step["step_index"] for step in result.steps] == [2, 3]
    assert result.failed_steps == [2]


def test_build_job_execution_result_failed_steps_ignore_non_failed_or_missing_model():
    runner = SimpleNamespace(
        model=SimpleNamespace(jid="job-1", name="Job", steps=[1, 2, 3]),
        status=RunnerStatus.FINISHED,
        _error=None,
        duration_ms=lambda: 500,
    )
    missing_model = SimpleNamespace(status=RunnerStatus.FAILED)
    completed = SimpleNamespace(
        model=SimpleNamespace(step_index=1, name="step-1", get_run_type=lambda: _RunType("command")),
        _run_type=None,
        status=RunnerStatus.COMPLETED,
        _error=None,
        duration_ms=lambda: 10,
    )
    failed = SimpleNamespace(
        model=SimpleNamespace(step_index=2, name="step-2", get_run_type=lambda: _RunType("command")),
        _run_type=None,
        status=RunnerStatus.FAILED,
        _error="boom",
        duration_ms=lambda: 20,
    )

    result = build_job_execution_result(
        runner,
        {"missing": missing_model, "1": completed, "2": failed},
    )

    assert result.failed_steps == [2]


def test_build_run_if_context_handles_empty_and_dependent_inputs():
    deps = [
        SimpleNamespace(is_success=True, is_failed=False, status=RunnerStatus.COMPLETED),
        SimpleNamespace(is_success=False, is_failed=True, status=RunnerStatus.CANCELED),
    ]

    empty_ctx = build_run_if_context([])
    dep_ctx = build_run_if_context(deps)

    assert empty_ctx["success"]() is True
    assert empty_ctx["failure"]() is False
    assert empty_ctx["canceled"]() is False
    assert empty_ctx["always"]() is True
    assert dep_ctx["success"]() is False
    assert dep_ctx["failure"]() is True
    assert dep_ctx["canceled"]() is True
    assert dep_ctx["always"]() is True
