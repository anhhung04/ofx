"""Tests for WorkflowExecutionManager."""

import pytest

from ofx.runner.execution.workflow_execution import (
    ExecutionResult,
    WorkflowExecutionManager,
)


class _ParentStub:
    def __init__(self):
        self._runners = {}
        self.logged = []

    def _child_context(self, update=None, **_kwargs):
        return {"ctx": "child", "update": update or {}}

    def _log_stage_failure(self, stage_index, errors):
        self.logged.append((stage_index, errors))


class _ResultStub:
    def __init__(self, error=None):
        self.error = error


class _RunnerStub:
    def __init__(self, should_raise=False, success=True, error="boom"):
        self._should_raise = should_raise
        self.is_success = success
        self._error = error

    async def run(self):
        if self._should_raise:
            raise RuntimeError("runner failed")
        return None

    async def get_result(self):
        return _ResultStub(self._error)


@pytest.mark.asyncio
async def test_run_stage_collects_errors():
    parent = _ParentStub()
    manager = WorkflowExecutionManager(parent)

    stage_runners = {
        "job1": _RunnerStub(should_raise=True, success=False, error="raised"),
        "job2": _RunnerStub(should_raise=False, success=False, error="failed"),
        "job3": _RunnerStub(should_raise=False, success=True, error=None),
    }

    errors, failed_jobs = await manager._run_stage(0, stage_runners)

    assert len(errors) == 2
    assert any("job1:" in err for err in errors)
    assert any("job 'job2': failed" in err for err in errors)
    assert set(failed_jobs) == {"job1", "job2"}
    assert parent.logged == [(0, errors)]


def test_build_stage_runners_creates_job_runners(monkeypatch):
    parent = _ParentStub()
    manager = WorkflowExecutionManager(parent)

    created = []

    class _DummyJobRunner:
        def __init__(self, job, ctx, parent):
            created.append(("job", job, ctx, parent))
            self.is_success = True

    class _DummyMatrixRunner:
        def __init__(self, job, ctx, parent):
            created.append(("matrix", job, ctx, parent))
            self.is_success = True

    monkeypatch.setattr(
        "ofx.runner.execution.workflow_execution.JobRunner", _DummyJobRunner
    )
    monkeypatch.setattr(
        "ofx.runner.execution.workflow_execution.MatrixJobRunner", _DummyMatrixRunner
    )

    class _Job:
        def __init__(self, matrix=False):
            self.strategy = type("S", (), {"matrix": True}) if matrix else None

    staged_jobs = {"a": _Job(matrix=False), "b": _Job(matrix=True)}
    stage_runners = manager._build_stage_runners(["a", "b"], staged_jobs)

    assert set(stage_runners.keys()) == {"a", "b"}
    assert parent._runners["a"] is stage_runners["a"]
    assert parent._runners["b"] is stage_runners["b"]
    assert [c[0] for c in created] == ["job", "matrix"]


@pytest.mark.asyncio
async def test_execution_result_collects_failed_jobs_and_stages():
    parent = _ParentStub()
    manager = WorkflowExecutionManager(parent)

    staged_jobs = {"a": object(), "b": object()}
    schedule = [["a"], ["b"]]

    class _RunnerFail(_RunnerStub):
        pass

    def _build_stage_runners(stage, _staged_jobs):
        if stage[0] == "a":
            return {"a": _RunnerFail(should_raise=False, success=False, error="fail")}
        return {"b": _RunnerStub(should_raise=False, success=True)}

    manager._build_stage_runners = _build_stage_runners  # type: ignore

    result = await manager.run(schedule, staged_jobs)
    assert isinstance(result, ExecutionResult)
    assert result.failed_stage_indices == [0]
    assert result.failed_job_ids == ["a"]
    assert len(result.errors) == 1
