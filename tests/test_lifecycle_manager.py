"""Focused tests for lifecycle manager helper behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ofx.runner import RunContext, RunnerStatus
from ofx.runner.lifecycle import LifecycleManager, RunnerStateMachine


class _RunnerStub:
    def __init__(self) -> None:
        self.run_id = "run-1"
        self.name = "runner"
        self.model = SimpleNamespace()
        self.ctx = RunContext()
        self.parent = None
        self._cached_durable_config = None
        self._state_machine = RunnerStateMachine()
        self._error = None
        self._registry = None
        self._warnings: list[str] = []
        self._debugs: list[str] = []
        self._cleanup_calls: list[str] = []
        self._started_at = None
        self._finished_at = None
        self._started_at_utc = None
        self._finished_at_utc = None

    async def reg_set_many(self, _items):
        return None

    async def _pre_run(self):
        return None

    async def _do_run(self):
        return None

    async def _post_run(self):
        return None

    async def _on_failure_cleanup(self):
        self._cleanup_calls.append("cleanup")

    async def get_result(self):
        return SimpleNamespace(status=RunnerStatus.COMPLETED, outputs={})

    def _log_warning(self, message: str) -> None:
        self._warnings.append(message)

    def _log_debug(self, message: str) -> None:
        self._debugs.append(message)

    @property
    def status(self):
        return self._state_machine.current_state


def _manager() -> LifecycleManager:
    return LifecycleManager(_RunnerStub())


def test_lifecycle_manager_uses_injected_event_emitter() -> None:
    runner = _RunnerStub()
    calls: list[tuple[str, object]] = []

    class _Emitter:
        def emit(self, event_type: str, payload=None) -> None:
            calls.append(("emit", event_type))

    manager = LifecycleManager(runner, event_emitter=_Emitter())
    manager._event_emitter.emit("runner_finish")

    assert calls == [("emit", "runner_finish")]


@pytest.mark.asyncio
async def test_execute_registers_metadata_and_filtered_context() -> None:
    manager = _manager()
    manager._runner.ctx = RunContext(inputs={"a": 1}, secrets={"x": "y"}, envs={"A": "1"})
    recorded: list[dict[str, dict[str, object]]] = []

    async def _reg_set_many(items):
        recorded.append(items)

    manager._runner.reg_set_many = _reg_set_many

    await manager.execute()

    items = recorded[0]

    assert items["metadata"]["run_id"] == "run-1"
    assert "secrets" not in items["context"]
    assert "envs" not in items["context"]
    assert manager._runner.status == RunnerStatus.COMPLETED


@pytest.mark.asyncio
async def test_handle_terminal_error_prefers_requested_state_then_failed() -> None:
    manager = _manager()

    await manager._handle_terminal_error(
        "cancelled",
        terminal_state=RunnerStatus.CANCELED,
        cleanup_required=False,
        cleanup_message="ignored",
    )
    assert manager._runner.status == RunnerStatus.CANCELED

    manager._runner._state_machine.set_state(RunnerStatus.RUNNING)
    await manager._handle_terminal_error(
        "boom",
        terminal_state=RunnerStatus.COMPLETED,
        cleanup_required=False,
        cleanup_message="ignored",
    )
    assert manager._runner.status == RunnerStatus.FAILED


def test_mark_finish_only_sets_timestamp_once(monkeypatch) -> None:
    manager = _manager()
    perf_values = iter([10.0, 99.0])
    utc_values = iter(["start-ts", "finish-ts", "ignored-ts"])

    monkeypatch.setattr(
        LifecycleManager,
        "_perf_counter_now",
        staticmethod(lambda: next(perf_values)),
    )
    monkeypatch.setattr(
        LifecycleManager,
        "_utc_now",
        staticmethod(lambda: next(utc_values)),
    )

    manager.mark_start()
    manager.mark_finish()
    first_finished_at = manager._runner._finished_at
    first_finished_at_utc = manager._runner._finished_at_utc
    manager.mark_finish()

    assert manager._runner._started_at == 10.0
    assert manager._runner._started_at_utc == "start-ts"
    assert first_finished_at == manager._runner._finished_at
    assert first_finished_at_utc == manager._runner._finished_at_utc


def test_duration_ms_uses_finished_time_when_available(monkeypatch) -> None:
    manager = _manager()
    manager._runner._started_at = 1.0
    manager._runner._finished_at = 2.5

    monkeypatch.setattr(
        LifecycleManager,
        "_perf_counter_now",
        staticmethod(lambda: 9.0),
    )

    assert manager.duration_ms() == 1500
    assert manager.duration_seconds() == 1.5


@pytest.mark.asyncio
async def test_write_final_checkpoints_attempts_second_write_when_status_changes(monkeypatch) -> None:
    manager = _manager()
    written_statuses: list[str] = []
    checkpoint_statuses = iter(["failed", "completed"])

    monkeypatch.setattr(
        "ofx.runner.lifecycle.normalized_runner_status_value",
        lambda _status: next(checkpoint_statuses),
    )

    async def _write_checkpoint(_self, status: str):
        written_statuses.append(status)

    monkeypatch.setattr(
        type(manager._checkpoint_manager),
        "write_checkpoint",
        _write_checkpoint,
    )

    await manager._write_final_checkpoints()

    assert written_statuses == ["failed", "completed"]


@pytest.mark.asyncio
async def test_write_final_checkpoints_logs_and_stops_after_initial_error(monkeypatch) -> None:
    manager = _manager()

    async def _write_checkpoint(_self, _status: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        type(manager._checkpoint_manager),
        "write_checkpoint",
        _write_checkpoint,
    )

    await manager._write_final_checkpoints()

    assert manager._runner._warnings == ["checkpoint write failed: boom"]


@pytest.mark.asyncio
async def test_handle_terminal_error_sets_failed_state_and_cleans_up() -> None:
    manager = _manager()

    await manager._handle_terminal_error(
        "boom",
        terminal_state=RunnerStatus.FAILED,
        cleanup_required=True,
        cleanup_message="Cleanup after pre_run failure failed",
    )

    assert manager._runner._error == "boom"
    assert manager._runner.status == RunnerStatus.FAILED
    assert manager._runner._cleanup_calls == ["cleanup"]


@pytest.mark.asyncio
async def test_handle_terminal_error_sets_canceled_state_and_optional_cleanup() -> None:
    manager = _manager()

    await manager._handle_terminal_error(
        "Cancelled: CancelledError",
        terminal_state=RunnerStatus.CANCELED,
        cleanup_required=True,
        cleanup_message="Cleanup after cancellation failed",
    )

    assert manager._runner._error == "Cancelled: CancelledError"
    assert manager._runner.status == RunnerStatus.CANCELED
    assert manager._runner._cleanup_calls == ["cleanup"]


@pytest.mark.asyncio
async def test_finalize_execution_emits_finish_and_cleans_registry(monkeypatch) -> None:
    manager = _manager()
    manager._runner._registry = object()
    manager._runner._error = "boom"
    manager._runner._state_machine.set_state(RunnerStatus.FAILED)
    events: list[tuple[str, object]] = []
    cleaned: list[object] = []
    pushed: list[str] = []

    class _Emitter:
        def emit(self, event_type: str, payload=None) -> None:
            events.append((event_type, payload))

    async def _write_final_checkpoints(_self):
        return None

    async def _cleanup_registry(registry):
        cleaned.append(registry)

    async def _auto_commit_push(_self):
        pushed.append("push")

    manager._event_emitter = _Emitter()
    monkeypatch.setattr(LifecycleManager, "_write_final_checkpoints", _write_final_checkpoints)
    monkeypatch.setattr(type(manager._checkpoint_manager), "auto_commit_push", _auto_commit_push)
    monkeypatch.setattr("ofx.runner.lifecycle.cleanup_registry", _cleanup_registry)

    await manager._finalize_execution()

    assert events == [("runner_finish", {"status": "failed", "error": "boom"})]
    assert cleaned == [manager._runner._registry]
    assert pushed == ["push"]
