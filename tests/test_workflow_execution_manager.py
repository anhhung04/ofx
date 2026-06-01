"""Focused tests for workflow execution manager helpers."""

from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ofx.runner import RunContext
from ofx.runner.workflow_execution import ExecutionResult, WorkflowExecutionManager


def _manager() -> WorkflowExecutionManager:
    parent = SimpleNamespace(
        ctx=RunContext(),
        _log_info=lambda _msg: None,
        _log_error=lambda _msg: None,
        _runners={},
        _time_guard=None,
    )
    return WorkflowExecutionManager(parent)


@pytest.mark.asyncio
async def test_run_records_failed_stage_indices_and_job_ids(monkeypatch) -> None:
    manager = _manager()
    created: list[tuple[object, bool, object]] = []

    monkeypatch.setattr(
        "ofx.runner.workflow_execution.job_runner_class",
        lambda _job: lambda job, ctx, *, parent: created.append(
            (job, ctx.allow_interactive, parent)
        ) or "runner:job-a",
    )

    async def _run_stage(stage_index, passed_runners):
        assert stage_index == 0
        assert passed_runners == {"job-a": "runner:job-a"}
        return ["job-a", "job-b"]

    monkeypatch.setattr(manager, "_run_stage", _run_stage)

    staged_job = object()

    result = await manager.run([["job-a"]], {"job-a": staged_job})

    assert result.failed_stage_indices == [0]
    assert result.failed_job_ids == ["job-a", "job-b"]
    assert created == [(staged_job, True, manager._parent)]


@pytest.mark.asyncio
async def test_run_skips_failure_recording_when_stage_succeeds(monkeypatch) -> None:
    manager = _manager()
    monkeypatch.setattr(
        "ofx.runner.workflow_execution.job_runner_class",
        lambda _job: lambda job, ctx, *, parent: "runner",
    )

    async def _run_stage(*_args, **_kwargs):
        return []

    monkeypatch.setattr(manager, "_run_stage", _run_stage)

    result = await manager.run([["job-a"]], {"job-a": object()})

    assert result.failed_stage_indices == []
    assert result.failed_job_ids == []


@pytest.mark.asyncio
async def test_run_registers_stage_children(monkeypatch) -> None:
    manager = _manager()
    created: list[tuple[object, bool, object]] = []

    monkeypatch.setattr(
        "ofx.runner.workflow_execution.job_runner_class",
        lambda _job: lambda job, ctx, *, parent: created.append(
            (job, ctx.allow_interactive, parent)
        ) or f"runner:{job}",
    )

    async def _run_stage(_stage_index, stage_runners):
        assert stage_runners == {"job-a": "runner:1", "job-b": "runner:2"}
        assert manager._parent._runners == stage_runners
        return []

    monkeypatch.setattr(manager, "_run_stage", _run_stage)

    result = await manager.run([["job-a", "job-b"]], {"job-a": 1, "job-b": 2})

    assert result.failed_stage_indices == []
    assert result.failed_job_ids == []
    assert created == [(1, False, manager._parent), (2, False, manager._parent)]


@pytest.mark.asyncio
async def test_run_stage_logs_start_message() -> None:
    messages: list[str] = []
    manager = WorkflowExecutionManager(
        SimpleNamespace(
            ctx=RunContext(),
            _log_info=messages.append,
            _log_error=lambda _msg: None,
            _runners={},
            _time_guard=None,
        )
    )

    await manager._run_stage(
        0,
        {
            "job-a": SimpleNamespace(is_failed=False, run=lambda: asyncio.sleep(0)),
            "job-b": SimpleNamespace(is_failed=False, run=lambda: asyncio.sleep(0)),
        },
    )

    assert messages == [
        f"Starting stage 1 with 2 job(s) (concurrency limit: {manager._max_parallel_jobs})"
    ]


@pytest.mark.asyncio
async def test_wait_for_memory_returns_immediately_when_limit_disabled(monkeypatch) -> None:
    manager = _manager()
    manager._mem_limit = 0

    sleep_calls: list[float] = []
    monkeypatch.setattr("asyncio.sleep", lambda delay: sleep_calls.append(delay))

    await manager._wait_for_memory()

    assert sleep_calls == []


@pytest.mark.asyncio
async def test_wait_for_memory_warns_once_until_usage_drops(monkeypatch) -> None:
    manager = _manager()
    manager._mem_limit = 75
    sleep_calls: list[float] = []
    warnings: list[tuple[str, float, int]] = []
    meminfo_reads = iter(
        [
            "MemTotal: 1000 kB\nMemAvailable: 200 kB\n",
            "MemTotal: 1000 kB\nMemAvailable: 210 kB\n",
            "MemTotal: 1000 kB\nMemAvailable: 500 kB\n",
        ]
    )

    monkeypatch.setattr("builtins.open", lambda *_args, **_kwargs: io.StringIO(next(meminfo_reads)))

    async def _sleep(delay: float):
        sleep_calls.append(delay)

    monkeypatch.setattr("asyncio.sleep", _sleep)
    monkeypatch.setattr(
        "ofx.runner.workflow_execution.logger.warning",
        lambda fmt, usage, limit: warnings.append((fmt, usage, limit)),
    )

    await manager._wait_for_memory()

    assert sleep_calls == [5, 5]
    assert warnings == [
        (
            "Memory usage %.0f%% exceeds limit %d%% - waiting before launching next job",
            80.0,
            75,
        )
    ]


@pytest.mark.asyncio
async def test_wait_for_memory_ignores_unreadable_meminfo(monkeypatch) -> None:
    manager = _manager()
    manager._mem_limit = 75

    monkeypatch.setattr("builtins.open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("boom")))

    await manager._wait_for_memory()


@pytest.mark.asyncio
async def test_run_builds_stage_runners_and_delegates(monkeypatch) -> None:
    manager = _manager()
    stage_runners = {"job-a": "runner:job-a"}

    monkeypatch.setattr(
        "ofx.runner.workflow_execution.job_runner_class",
        lambda _job: lambda job, ctx, *, parent: "runner:job-a",
    )

    async def _run_stage(stage_index, passed_runners):
        assert stage_index == 0
        assert passed_runners == stage_runners
        return ["job-a"]

    monkeypatch.setattr(manager, "_run_stage", _run_stage)

    result = await manager.run([["job-a"]], {"job-a": object()})

    assert result.failed_stage_indices == [0]
    assert result.failed_job_ids == ["job-a"]


@pytest.mark.asyncio
async def test_run_aborts_remaining_stages_when_time_guard_requests_abort(monkeypatch) -> None:
    manager = _manager()
    manager._parent._time_guard = SimpleNamespace(should_abort=True)

    monkeypatch.setattr(
        "ofx.runner.workflow_execution.job_runner_class",
        lambda _job: (
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("should not build any stage")
            )
        ),
    )

    result = await manager.run([["job-a"], ["job-b", "job-c"]], {})

    assert result.failed_stage_indices == [0]
    assert result.failed_job_ids == ["job-a", "job-b", "job-c"]


@pytest.mark.asyncio
async def test_run_stage_returns_failed_job_ids() -> None:
    manager = _manager()

    failed_jobs = await manager._run_stage(
        0,
        {
            "job-a": SimpleNamespace(is_failed=False, run=lambda: asyncio.sleep(0)),
            "job-b": SimpleNamespace(is_failed=True, run=lambda: asyncio.sleep(0)),
        },
    )

    assert failed_jobs == ["job-b"]


@pytest.mark.asyncio
async def test_run_stage_logs_task_exceptions() -> None:
    async def _boom() -> None:
        raise RuntimeError("boom")

    with patch("ofx.runner.workflow_execution.logger.debug") as debug_log:
        failed_jobs = await _manager()._run_stage(
            0,
            {"job-a": SimpleNamespace(is_failed=True, run=_boom)},
        )

    assert failed_jobs == ["job-a"]
    debug_log.assert_called_once()
    assert debug_log.call_args.args[:2] == ("Job '%s' raised: %s", "job-a")
    assert str(debug_log.call_args.args[2]) == "boom"
