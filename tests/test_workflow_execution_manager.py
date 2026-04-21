"""Tests for WorkflowExecutionManager."""

import pytest

from ofx.runner.execution.workflow_execution import (
    ExecutionResult,
    WorkflowExecutionManager,
)


class _ParentStub:
    def __init__(self):
        self._runners = {}

    def _child_context(self, update=None, **_kwargs):
        return {"ctx": "child", "update": update or {}}

    def _log_info(self, msg):
        pass


class _ResultStub:
    def __init__(self, error=None):
        self.error = error


class _RunnerStub:
    def __init__(self, should_raise=False, success=True, error="boom"):
        self._should_raise = should_raise
        self.is_success = success
        self.is_failed = not success
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

    failed_jobs = await manager._run_stage(0, stage_runners)

    assert set(failed_jobs) == {"job1", "job2"}


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
        "ofx.runner.execution.job.JobRunner", _DummyJobRunner
    )
    monkeypatch.setattr(
        "ofx.runner.execution.job.MatrixJobRunner", _DummyMatrixRunner
    )

    class _DummyCloudRunner:
        def __init__(self, job, ctx, parent, cloud_config=None):
            created.append(("cloud", job, ctx, parent))
            self.is_success = True

    class _DummyCloudMatrixRunner:
        def __init__(self, job, ctx, parent):
            created.append(("cloud_matrix", job, ctx, parent))
            self.is_success = True

    monkeypatch.setattr(
        "ofx.runner.execution.cloud_job.CloudJobRunner", _DummyCloudRunner
    )
    monkeypatch.setattr(
        "ofx.runner.execution.cloud_matrix.CloudMatrixJobRunner",
        _DummyCloudMatrixRunner,
    )

    class _Job:
        def __init__(self, matrix=False, cloud=None, fleet=False):
            if matrix and fleet:
                self.strategy = type(
                    "S", (), {"matrix": True, "fleet": True}
                )()
            elif matrix:
                self.strategy = type(
                    "S", (), {"matrix": True, "fleet": None}
                )()
            elif fleet:
                self.strategy = type(
                    "S", (), {"matrix": None, "fleet": True}
                )()
            else:
                self.strategy = None
            self.cloud = cloud

    staged_jobs = {"a": _Job(matrix=False), "b": _Job(matrix=True)}
    stage_runners = manager._build_stage_runners(["a", "b"], staged_jobs)

    assert set(stage_runners.keys()) == {"a", "b"}
    assert parent._runners["a"] is stage_runners["a"]
    assert parent._runners["b"] is stage_runners["b"]
    assert [c[0] for c in created] == ["job", "matrix"]


def test_build_stage_runners_cloud_job(monkeypatch):
    """Cloud job without matrix/fleet → CloudJobRunner."""
    parent = _ParentStub()
    manager = WorkflowExecutionManager(parent)

    created = []

    class _DummyCloudRunner:
        def __init__(self, job, ctx, parent, cloud_config=None):
            created.append(("cloud", job))
            self.is_success = True

    monkeypatch.setattr(
        "ofx.runner.execution.cloud_job.CloudJobRunner", _DummyCloudRunner
    )

    class _Job:
        def __init__(self):
            self.cloud = "some-profile"
            self.strategy = None

    staged_jobs = {"c": _Job()}
    stage_runners = manager._build_stage_runners(["c"], staged_jobs)

    assert "c" in stage_runners
    assert created[0][0] == "cloud"


def test_build_stage_runners_cloud_matrix(monkeypatch):
    """Cloud + matrix → CloudMatrixJobRunner."""
    parent = _ParentStub()
    manager = WorkflowExecutionManager(parent)

    created = []

    class _DummyCloudMatrixRunner:
        def __init__(self, job, ctx, parent):
            created.append(("cloud_matrix", job))
            self.is_success = True

    monkeypatch.setattr(
        "ofx.runner.execution.cloud_matrix.CloudMatrixJobRunner",
        _DummyCloudMatrixRunner,
    )

    class _Job:
        def __init__(self):
            self.cloud = "some-profile"
            self.strategy = type("S", (), {"matrix": {"os": ["a"]}, "fleet": None})()

    staged_jobs = {"d": _Job()}
    _stage_runners = manager._build_stage_runners(["d"], staged_jobs)

    assert created[0][0] == "cloud_matrix"


def test_build_stage_runners_cloud_fleet(monkeypatch):
    """Cloud + fleet → CloudFleetRunner."""
    parent = _ParentStub()
    manager = WorkflowExecutionManager(parent)

    created = []

    class _DummyCloudFleetRunner:
        def __init__(self, job, ctx, parent):
            created.append(("cloud_fleet", job))
            self.is_success = True

    monkeypatch.setattr(
        "ofx.runner.execution.cloud_fleet.CloudFleetRunner",
        _DummyCloudFleetRunner,
    )

    class _Job:
        def __init__(self):
            self.cloud = "some-profile"
            self.strategy = type("S", (), {"matrix": None, "fleet": True})()

    staged_jobs = {"e": _Job()}
    _stage_runners = manager._build_stage_runners(["e"], staged_jobs)

    assert created[0][0] == "cloud_fleet"


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
