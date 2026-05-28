"""Runner lifecycle orchestration and state management."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ofx.runner.context import ConditionNotMetError, RunnerStatus, RunResult
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

    def __init__(self, runner: Runner[Any]) -> None:
        self._runner = runner
        self._event_emitter = EventEmitter(runner)
        self._checkpoint_manager = CheckpointManager(runner)

    async def execute(self) -> RunResult:
        self.mark_start()
        self.emit_event("runner_start")
        if await self.restore_from_checkpoint():
            self.emit_event("runner_resume")
            return await self._runner.get_result()
        await self.write_checkpoint("running")
        pre_run_ok = False
        try:
            await self._runner.reg_set_many(
                {
                    "metadata": {
                        "run_id": self._runner.run_id,
                        "name": self._runner.name,
                        "type": str(type(self._runner.model)),
                    },
                    "context": self._runner.ctx.model_dump(
                        exclude={"secrets", "envs"}
                    ),
                }
            )

            await self._runner._pre_run()
            pre_run_ok = True
            self._runner._state_machine.transition(RunnerStatus.RUNNING)
            await self._runner._do_run()
            self._runner._state_machine.transition(RunnerStatus.FINISHED)
            await self._runner._post_run()
            self._runner._state_machine.transition(RunnerStatus.COMPLETED)
        except (asyncio.CancelledError, KeyboardInterrupt) as exc:
            self._runner._error = f"Cancelled: {type(exc).__name__}"
            self._transition_on_cancellation()
            if pre_run_ok:
                await self._cleanup_after_failure("Cleanup after cancellation failed")
            raise
        except ConditionNotMetError as exc:
            self._runner._error = str(exc)
            if self._runner._state_machine.can_transition(RunnerStatus.CANCELED):
                self._runner._state_machine.transition(RunnerStatus.CANCELED)
            elif self._runner._state_machine.current_state not in (
                RunnerStatus.FAILED,
                RunnerStatus.CANCELED,
            ):
                self._runner._state_machine.transition(RunnerStatus.FAILED)
            if pre_run_ok:
                await self._cleanup_after_failure("Cleanup after failure failed")
        except Exception as exc:
            self._runner._error = str(exc)
            if self._runner._state_machine.current_state not in (
                RunnerStatus.FAILED,
                RunnerStatus.CANCELED,
            ):
                self._runner._state_machine.transition(RunnerStatus.FAILED)
            if pre_run_ok:
                await self._cleanup_after_failure("Cleanup after failure failed")
            else:
                await self._cleanup_after_failure(
                    "Cleanup after pre_run failure failed"
                )
        finally:
            self.mark_finish()
            self.emit_event(
                "runner_finish",
                {"status": self._runner.status.value, "error": self._runner._error},
            )
            initial_checkpoint_status = self.checkpoint_status()
            try:
                await self.write_checkpoint(initial_checkpoint_status)
            except Exception as checkpoint_err:
                self._runner._log_warning(
                    f"checkpoint write failed: {checkpoint_err}"
                )

            final_status = self.checkpoint_status()
            if final_status != initial_checkpoint_status:
                try:
                    await self.write_checkpoint(final_status)
                except Exception as checkpoint_err:
                    self._runner._log_warning(
                        "final checkpoint update skipped due to error: "
                        f"{checkpoint_err}"
                    )

            try:
                if self._runner._registry is not None:
                    await cleanup_registry(self._runner._registry)
            except Exception as cleanup_err:
                self._runner._log_warning(f"registry cleanup failed: {cleanup_err}")

            await self.auto_commit_push()
        return await self._runner.get_result()

    def add_event_listener(self, event_type: str, callback: Any) -> None:
        self._event_emitter.add_event_listener(event_type, callback)

    def emit_event(
        self, event_type: str, payload: dict[str, Any] | None = None
    ) -> None:
        self._event_emitter.emit(event_type, payload)

    async def write_checkpoint(self, status: str) -> None:
        await self._checkpoint_manager.write_checkpoint(status)

    async def restore_from_checkpoint(self) -> bool:
        return await self._checkpoint_manager.restore_from_checkpoint()

    def durable_config(self):
        return self._checkpoint_manager.durable_config()

    def checkpoint_id(self) -> str:
        return self._checkpoint_manager.checkpoint_id()

    def checkpoint_status(self) -> str:
        return self._checkpoint_manager.checkpoint_status()

    async def auto_commit_push(self) -> None:
        await self._checkpoint_manager.auto_commit_push()

    def mark_start(self) -> None:
        self._runner._started_at = time.perf_counter()
        self._runner._started_at_utc = datetime.now(UTC).isoformat()

    def mark_finish(self) -> None:
        if self._runner._finished_at is None:
            self._runner._finished_at = time.perf_counter()
            self._runner._finished_at_utc = datetime.now(UTC).isoformat()

    def duration_ms(self) -> int | None:
        if self._runner._started_at is None:
            return None
        end = self._runner._finished_at or time.perf_counter()
        return int((end - self._runner._started_at) * 1000)

    def duration_seconds(self) -> float | None:
        duration_ms = self.duration_ms()
        if duration_ms is None:
            return None
        return duration_ms / 1000.0

    async def _cleanup_after_failure(self, message: str) -> None:
        try:
            await self._runner._on_failure_cleanup()
        except Exception as cleanup_exc:
            self._runner._log_debug(f"{message}: {cleanup_exc}")

    def _transition_on_cancellation(self) -> None:
        if self._runner._state_machine.can_transition(RunnerStatus.CANCELED):
            self._runner._state_machine.transition(RunnerStatus.CANCELED)
        elif self._runner._state_machine.current_state not in (
            RunnerStatus.FAILED,
            RunnerStatus.CANCELED,
        ):
            self._runner._state_machine.transition(RunnerStatus.FAILED)
