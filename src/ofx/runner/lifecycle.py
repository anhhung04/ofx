"""Runner lifecycle orchestration and state management."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ofx.runner.context import (
    ConditionNotMetError,
    RunnerStatus,
    RunResult,
    normalized_runner_status_value,
)
from ofx.runner.registry import cleanup_registry
from ofx.runner.services.checkpoint import CheckpointManager
from ofx.runner.services.event_emitter import EventEmitter

if TYPE_CHECKING:
    from ofx.runner.runner import Runner

class RunnerStateMachine:
    """Finite State Machine for managing runner execution states."""

    __slots__ = ("_current_state", "_transitions")

    def __init__(self) -> None:
        self._current_state = RunnerStatus.IDLE
        self._transitions = {
            RunnerStatus.IDLE: [
                RunnerStatus.RUNNING,
                RunnerStatus.CANCELED,
                RunnerStatus.FAILED,
            ],
            RunnerStatus.RUNNING: [
                RunnerStatus.FINISHED,
                RunnerStatus.FAILED,
                RunnerStatus.CANCELED,
            ],
            RunnerStatus.FINISHED: [
                RunnerStatus.COMPLETED,
                RunnerStatus.FAILED,
                RunnerStatus.CANCELED,
            ],
            RunnerStatus.FAILED: [],
            RunnerStatus.COMPLETED: [],
            RunnerStatus.CANCELED: [],
        }

    def can_transition(self, to_state: RunnerStatus) -> bool:
        return to_state in self._transitions[self._current_state]

    def transition(self, to_state: RunnerStatus) -> None:
        if not self.can_transition(to_state):
            raise ValueError(
                f"Invalid state transition from {self._current_state} to {to_state}"
            )
        self._current_state = to_state

    @property
    def current_state(self) -> RunnerStatus:
        return self._current_state

    @property
    def is_terminal(self) -> bool:
        return not self._transitions[self._current_state]

    def set_state(self, state: RunnerStatus) -> None:
        self._current_state = state

class LifecycleManager:
    """Coordinate runner execution, state transitions, and timing."""

    __slots__ = ("_runner", "_event_emitter", "_checkpoint_manager")

    def __init__(
        self,
        runner: Runner[Any],
        *,
        event_emitter: EventEmitter | None = None,
    ) -> None:
        self._runner = runner
        self._event_emitter = event_emitter or EventEmitter(runner)
        self._checkpoint_manager = CheckpointManager(runner)

    def checkpoint_id(self) -> str:
        return self._checkpoint_manager.checkpoint_id()

    async def execute(self) -> RunResult:
        self.mark_start()
        self._event_emitter.emit("runner_start")
        if await self._checkpoint_manager.restore_from_checkpoint():
            self._event_emitter.emit("runner_resume")
            return await self._runner.get_result()
        await self._checkpoint_manager.write_checkpoint("running")
        pre_run_ok = False
        try:
            await self._runner.reg_set_many(
                {
                    "metadata": {
                        "run_id": self._runner.run_id,
                        "name": self._runner.name,
                        "type": str(type(self._runner.model)),
                    },
                    "context": self._runner.ctx.model_dump(exclude={"secrets", "envs"}),
                }
            )
            await self._runner._pre_run()
            self._runner._state_machine.transition(RunnerStatus.RUNNING)
            await self._runner._do_run()
            self._runner._state_machine.transition(RunnerStatus.FINISHED)
            await self._runner._post_run()
            self._runner._state_machine.transition(RunnerStatus.COMPLETED)
            pre_run_ok = True
        except (asyncio.CancelledError, KeyboardInterrupt) as exc:
            await self._handle_terminal_error(
                f"Cancelled: {type(exc).__name__}",
                terminal_state=RunnerStatus.CANCELED,
                cleanup_required=pre_run_ok,
                cleanup_message="Cleanup after cancellation failed",
            )
            raise
        except ConditionNotMetError as exc:
            await self._handle_terminal_error(
                str(exc),
                terminal_state=RunnerStatus.CANCELED,
                cleanup_required=pre_run_ok,
                cleanup_message="Cleanup after failure failed",
            )
        except Exception as exc:
            await self._handle_terminal_error(
                str(exc),
                terminal_state=RunnerStatus.FAILED,
                cleanup_required=True,
                cleanup_message=(
                    "Cleanup after failure failed"
                    if pre_run_ok
                    else "Cleanup after pre_run failure failed"
                ),
            )
        finally:
            await self._finalize_execution()
        return await self._runner.get_result()

    async def _finalize_execution(self) -> None:
        self.mark_finish()
        self._event_emitter.emit(
            "runner_finish",
            {
                "status": self._runner.status.value,
                "error": self._runner._error,
            },
        )
        await self._write_final_checkpoints()
        try:
            if self._runner._registry is not None:
                await cleanup_registry(self._runner._registry)
        except Exception as cleanup_err:
            self._runner._log_warning(f"registry cleanup failed: {cleanup_err}")
        await self._checkpoint_manager.auto_commit_push()

    async def _write_final_checkpoints(self) -> None:
        initial_checkpoint_status = normalized_runner_status_value(self._runner.status)
        try:
            await self._checkpoint_manager.write_checkpoint(initial_checkpoint_status)
        except Exception as checkpoint_err:
            self._runner._log_warning(f"checkpoint write failed: {checkpoint_err}")
            return

        final_status = normalized_runner_status_value(self._runner.status)
        if final_status != initial_checkpoint_status:
            try:
                await self._checkpoint_manager.write_checkpoint(final_status)
            except Exception as checkpoint_err:
                self._runner._log_warning(
                    f"final checkpoint update skipped due to error: {checkpoint_err}"
                )

    def _set_timestamp_fields(self, prefix: str) -> None:
        setattr(self._runner, f"_{prefix}_at", self._perf_counter_now())
        setattr(self._runner, f"_{prefix}_at_utc", self._utc_now())

    def mark_start(self) -> None:
        self._set_timestamp_fields("started")

    def mark_finish(self) -> None:
        if self._runner._finished_at is not None:
            return
        self._set_timestamp_fields("finished")

    @staticmethod
    def _perf_counter_now() -> float:
        return time.perf_counter()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(UTC).isoformat()

    def duration_ms(self) -> int | None:
        started_at = self._runner._started_at
        if started_at is None:
            return None
        finished_at = self._runner._finished_at or self._perf_counter_now()
        return int((finished_at - started_at) * 1000)

    def duration_seconds(self) -> float | None:
        duration_ms = self.duration_ms()
        if duration_ms is None:
            return None
        return duration_ms / 1000.0

    def _transition_to_terminal_state(self, terminal_state: RunnerStatus) -> None:
        if self._runner._state_machine.can_transition(terminal_state):
            self._runner._state_machine.transition(terminal_state)
            return
        if self._runner._state_machine.current_state not in (
            RunnerStatus.FAILED,
            RunnerStatus.CANCELED,
        ):
            self._runner._state_machine.transition(RunnerStatus.FAILED)

    async def _handle_terminal_error(
        self,
        error: str,
        *,
        terminal_state: RunnerStatus,
        cleanup_required: bool,
        cleanup_message: str,
    ) -> None:
        self._runner._error = error
        self._transition_to_terminal_state(terminal_state)
        if cleanup_required:
            try:
                await self._runner._on_failure_cleanup()
            except Exception as cleanup_exc:
                self._runner._log_debug(f"{cleanup_message}: {cleanup_exc}")
