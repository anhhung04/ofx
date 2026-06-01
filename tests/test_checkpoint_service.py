from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ofx.models.config import DurableRunConfig
from ofx.runner import RunContext, RunnerStatus
from ofx.runner.services.checkpoint import CheckpointManager


class FakeRunner:
    def __init__(
        self,
        *,
        model,
        ctx: RunContext,
        parent=None,
        run_id: str = "run-1",
    ) -> None:
        self.model = model
        self.ctx = ctx
        self.parent = parent
        self.run_id = run_id
        self._error = None
        self._started_at_utc = None
        self._finished_at_utc = None
        self._cached_durable_config = None
        self._state_machine = SimpleNamespace(set_state=lambda _state: None)
        self._state_machine.is_terminal = True
        self.reg_set = AsyncMock()
        self._warnings: list[str] = []

    @property
    def started_at(self):
        return "2026-01-01T00:00:00+00:00"

    @property
    def finished_at(self):
        return "2026-01-01T00:01:00+00:00"

    @property
    def status(self):
        return RunnerStatus.COMPLETED

    def duration_ms(self):
        return 60000

    async def get_result(self):
        return SimpleNamespace(outputs={"status": "ok"})

    def _log_warning(self, message: str) -> None:
        self._warnings.append(message)


def _parent(*, checkpoint_id: str = "workflow/WorkflowRunner:Parent", durable=None):
    return SimpleNamespace(
        run_id="parent-run",
        ctx=RunContext(durable=durable),
        _checkpoint_id=lambda: checkpoint_id,
    )


def test_checkpoint_id_uses_parent_job_and_name_paths():
    durable = DurableRunConfig(enabled=True, backend="file")

    named_runner = FakeRunner(
        model=SimpleNamespace(name="Named Workflow"),
        ctx=RunContext(durable=durable),
    )
    manager = CheckpointManager(named_runner)
    assert manager.checkpoint_id() == "workflow/FakeRunner:Named Workflow"

    job_runner = FakeRunner(
        model=SimpleNamespace(jid="job-1"),
        ctx=RunContext(durable=durable),
        parent=_parent(),
    )
    assert CheckpointManager(job_runner).checkpoint_id() == (
        "workflow/WorkflowRunner:Parent/job:job-1"
    )

    step_runner = FakeRunner(
        model=SimpleNamespace(jid="job-1", step_index=2),
        ctx=RunContext(durable=durable),
        parent=_parent(),
    )
    assert CheckpointManager(step_runner).checkpoint_id() == (
        "workflow/WorkflowRunner:Parent/job:job-1:2"
    )


def test_checkpoint_id_prefers_parent_lifecycle_when_present():
    durable = DurableRunConfig(enabled=True, backend="file")

    parent_runner = SimpleNamespace(
        run_id="parent-run",
        ctx=RunContext(durable=durable),
        _lifecycle=SimpleNamespace(
            checkpoint_id=lambda: "workflow/WorkflowRunner:LifecycleParent"
        ),
    )
    child_runner = FakeRunner(
        model=SimpleNamespace(jid="job-1"),
        ctx=RunContext(durable=durable),
        parent=parent_runner,
    )

    assert CheckpointManager(child_runner).checkpoint_id() == (
        "workflow/WorkflowRunner:LifecycleParent/job:job-1"
    )


def test_durable_config_prefers_runner_then_parent_and_caches():
    parent_durable = DurableRunConfig(enabled=True, backend="file")
    runner_durable = DurableRunConfig(enabled=True, backend="redis")

    parent_only_runner = FakeRunner(
        model=SimpleNamespace(name="wf"),
        ctx=RunContext(durable=None),
        parent=_parent(durable=parent_durable),
    )
    parent_only_manager = CheckpointManager(parent_only_runner)
    assert parent_only_manager.durable_config() is parent_durable
    assert parent_only_manager.durable_config() is parent_durable

    runner_first = FakeRunner(
        model=SimpleNamespace(name="wf"),
        ctx=RunContext(durable=runner_durable),
        parent=_parent(durable=parent_durable),
    )
    assert CheckpointManager(runner_first).durable_config() is runner_durable


@pytest.mark.asyncio
async def test_restore_from_checkpoint_restores_empty_outputs(monkeypatch, tmp_path):
    durable = DurableRunConfig(enabled=True, resume=True, backend="file")
    runner = FakeRunner(
        model=SimpleNamespace(name="wf"),
        ctx=RunContext(output_path=tmp_path, durable=durable),
    )
    manager = CheckpointManager(runner)

    monkeypatch.setattr(
        "ofx.runner.services.checkpoint.get_checkpoint",
        AsyncMock(
            return_value={
                "status": "completed",
                "error": None,
                "started_at": "2026-01-01T00:00:00+00:00",
                "finished_at": "2026-01-01T00:01:00+00:00",
                "outputs": {},
            }
        ),
    )

    restored = await manager.restore_from_checkpoint()

    assert restored is True
    runner.reg_set.assert_awaited_once_with("outputs", {})


@pytest.mark.asyncio
async def test_restore_from_checkpoint_restores_error_timestamps_and_completed_status(monkeypatch, tmp_path):
    durable = DurableRunConfig(enabled=True, backend="file")
    state_calls: list[RunnerStatus] = []
    runner = FakeRunner(
        model=SimpleNamespace(name="wf"),
        ctx=RunContext(output_path=tmp_path, durable=DurableRunConfig(enabled=True, resume=True, backend="file")),
    )
    runner._state_machine = SimpleNamespace(set_state=lambda state: state_calls.append(state))
    manager = CheckpointManager(runner)

    monkeypatch.setattr(
        "ofx.runner.services.checkpoint.get_checkpoint",
        AsyncMock(
            return_value={
                "status": "completed",
                "error": "boom",
                "started_at": "2026-01-01T00:00:00+00:00",
                "finished_at": "2026-01-01T00:01:00+00:00",
                "outputs": {},
            }
        ),
    )

    restored = await manager.restore_from_checkpoint()

    assert restored is True
    assert runner._error == "boom"
    assert runner._started_at_utc == "2026-01-01T00:00:00+00:00"
    assert runner._finished_at_utc == "2026-01-01T00:01:00+00:00"
    assert state_calls == [RunnerStatus.COMPLETED]


@pytest.mark.asyncio
async def test_checkpoint_operations_require_config_output_path_and_resume(
    tmp_path: Path,
    monkeypatch,
):
    durable = DurableRunConfig(enabled=True, resume=True, backend="file")
    runner = FakeRunner(
        model=SimpleNamespace(name="wf"),
        ctx=RunContext(output_path=tmp_path, durable=durable),
    )
    manager = CheckpointManager(runner)

    write_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "ofx.runner.services.checkpoint.write_checkpoint",
        AsyncMock(side_effect=lambda _output_path, _config, _checkpoint_id, payload: write_calls.append(dict(payload))),
    )

    await manager.write_checkpoint("running")
    assert write_calls == [
        {
            "run_id": "run-1",
            "checkpoint_id": "workflow/FakeRunner:wf",
            "status": "running",
            "runner_type": "FakeRunner",
            "model_type": "SimpleNamespace",
            "name": "wf",
            "parent_run_id": None,
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:01:00+00:00",
            "duration_ms": 60000,
            "error": None,
            "job_id": None,
            "step_index": None,
        }
    ]

    runner.ctx.output_path = None
    await manager.write_checkpoint("completed")
    assert len(write_calls) == 1

    restore_calls: list[str] = []

    monkeypatch.setattr(
        "ofx.runner.services.checkpoint.get_checkpoint",
        AsyncMock(side_effect=lambda *_args, **_kwargs: restore_calls.append("called") or {"status": "completed"}),
    )

    assert await manager.restore_from_checkpoint() is False
    assert restore_calls == []

    runner.ctx.output_path = tmp_path
    runner.ctx.durable = DurableRunConfig(enabled=True, resume=False, backend="file")
    runner._cached_durable_config = None

    assert await manager.restore_from_checkpoint() is False
    assert restore_calls == []


@pytest.mark.asyncio
async def test_write_checkpoint_adds_outputs_only_when_not_running(monkeypatch, tmp_path):
    durable = DurableRunConfig(enabled=True, backend="file")
    runner = FakeRunner(
        model=SimpleNamespace(name="wf"),
        ctx=RunContext(output_path=tmp_path, durable=durable),
    )
    manager = CheckpointManager(runner)

    captured: list[dict[str, object]] = []

    monkeypatch.setattr(
        "ofx.runner.services.checkpoint.write_checkpoint",
        AsyncMock(side_effect=lambda _output_path, _config, _checkpoint_id, payload: captured.append(dict(payload))),
    )

    await manager.write_checkpoint("running")
    await manager.write_checkpoint("completed")

    assert "outputs" not in captured[0]
    assert captured[1]["outputs"] == {"status": "ok"}


@pytest.mark.asyncio
async def test_write_checkpoint_warns_and_stores_empty_outputs_on_result_error(monkeypatch, tmp_path):
    durable = DurableRunConfig(enabled=True, backend="file")
    runner = FakeRunner(
        model=SimpleNamespace(name="wf"),
        ctx=RunContext(output_path=tmp_path, durable=durable),
    )

    runner.get_result = AsyncMock(side_effect=RuntimeError("boom"))
    manager = CheckpointManager(runner)

    captured: list[dict[str, object]] = []

    monkeypatch.setattr(
        "ofx.runner.services.checkpoint.write_checkpoint",
        AsyncMock(side_effect=lambda _output_path, _config, _checkpoint_id, payload: captured.append(dict(payload))),
    )

    await manager.write_checkpoint("completed")

    assert captured[0]["outputs"] == {}
    assert runner._warnings == ["Failed to retrieve outputs for checkpoint: boom"]


@pytest.mark.asyncio
async def test_restore_from_checkpoint_requires_completed_status(monkeypatch, tmp_path):
    durable = DurableRunConfig(enabled=True, resume=True, backend="file")
    runner = FakeRunner(
        model=SimpleNamespace(name="wf"),
        ctx=RunContext(output_path=tmp_path, durable=durable),
    )
    manager = CheckpointManager(runner)

    monkeypatch.setattr(
        "ofx.runner.services.checkpoint.get_checkpoint",
        AsyncMock(return_value={"status": "running"}),
    )

    restored = await manager.restore_from_checkpoint()

    assert restored is False


@pytest.mark.asyncio
async def test_auto_commit_push_respects_runner_state_and_formats_message(
    monkeypatch,
    tmp_path: Path,
):
    durable = DurableRunConfig(enabled=True, auto_commit=True, backend="file")
    runner = FakeRunner(
        model=SimpleNamespace(name="Named Workflow"),
        ctx=RunContext(output_path=tmp_path, durable=durable),
    )
    manager = CheckpointManager(runner)
    captured: list[tuple[Path, dict[str, object]]] = []

    monkeypatch.setattr(
        "ofx.runner.services.checkpoint.commit_and_push",
        AsyncMock(side_effect=lambda path, **kwargs: captured.append((path, kwargs))),
    )

    await manager.auto_commit_push()

    assert captured == [
        (
            tmp_path,
            {
                "do_commit": True,
                "do_push": False,
                "message": "checkpoint: Named Workflow [completed]",
            },
        )
    ]

    runner.parent = _parent(durable=durable)
    await manager.auto_commit_push()
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_auto_commit_push_passes_flags_and_logs_failure(
    monkeypatch,
    tmp_path: Path,
):
    durable = DurableRunConfig(
        enabled=True,
        auto_commit=True,
        auto_push=True,
        backend="file",
    )
    runner = FakeRunner(
        model=SimpleNamespace(name="Named Workflow"),
        ctx=RunContext(output_path=tmp_path, durable=durable),
    )
    manager = CheckpointManager(runner)

    captured: list[tuple[Path, dict[str, object]]] = []

    monkeypatch.setattr(
        "ofx.runner.services.checkpoint.commit_and_push",
        AsyncMock(
            side_effect=lambda path, **kwargs: captured.append((path, kwargs))
            or (_ for _ in ()).throw(RuntimeError("boom"))
        ),
    )

    await manager.auto_commit_push()

    assert captured == [
        (
            tmp_path,
            {
                "do_commit": True,
                "do_push": True,
                "message": "checkpoint: Named Workflow [completed]",
            },
        )
    ]
    assert runner._warnings == ["auto-commit/push failed: boom"]
