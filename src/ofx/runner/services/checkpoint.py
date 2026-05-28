"""Durable checkpoint lifecycle helpers for runners."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ofx.runner.context import RunnerStatus
from ofx.runner.durable import get_checkpoint, write_checkpoint
from ofx.runner.durable_git import commit_and_push
from ofx.runner.registry_keys import RunnerRegistryKeys

if TYPE_CHECKING:
    from ofx.runner.runner import Runner


class CheckpointManager:
    """Manage durable checkpoint persistence and restoration."""

    __slots__ = ("_runner",)

    def __init__(self, runner: Runner[Any]) -> None:
        self._runner = runner

    async def write_checkpoint(self, status: str) -> None:
        config = self.durable_config()
        if not config or not self._runner.ctx.output_path:
            return

        payload: dict[str, Any] = {
            "run_id": self._runner.run_id,
            "checkpoint_id": self.checkpoint_id(),
            "status": status,
            "runner_type": self._runner.__class__.__name__,
            "model_type": type(self._runner.model).__name__,
            "name": getattr(self._runner.model, "name", None),
            "parent_run_id": self._runner.parent.run_id if self._runner.parent else None,
            "started_at": self._runner.started_at,
            "finished_at": self._runner.finished_at,
            "duration_ms": self._runner.duration_ms(),
            "error": self._runner._error,
            "job_id": getattr(self._runner.model, "jid", None),
            "step_index": getattr(self._runner.model, "step_index", None),
        }

        if status != "running":
            try:
                result = await self._runner.get_result()
                payload["outputs"] = result.outputs
            except Exception as exc:
                self._runner._log_warning(
                    f"Failed to retrieve outputs for checkpoint: {exc}"
                )
                payload["outputs"] = {}

        await write_checkpoint(
            self._runner.ctx.output_path,
            config,
            self.checkpoint_id(),
            payload,
        )

    async def restore_from_checkpoint(self) -> bool:
        config = self.durable_config()
        if not config or not config.resume or not self._runner.ctx.output_path:
            return False

        checkpoint = await get_checkpoint(
            self._runner.ctx.output_path,
            config,
            self.checkpoint_id(),
        )
        if not checkpoint or checkpoint.get("status") != "completed":
            return False

        self._runner._error = checkpoint.get("error")
        self._runner._durable_outputs = checkpoint.get("outputs", {})
        self._runner._started_at_utc = checkpoint.get("started_at")
        self._runner._finished_at_utc = checkpoint.get("finished_at")
        self._runner._state_machine.set_state(RunnerStatus.COMPLETED)
        if self._runner._durable_outputs is not None:
            await self._runner.reg_set(
                RunnerRegistryKeys.OUTPUTS, self._runner._durable_outputs
            )
        return True

    def durable_config(self):
        """Return the durable config, cached after first lookup."""
        if self._runner._cached_durable_config is not None:
            return self._runner._cached_durable_config
        if self._runner.ctx.durable and self._runner.ctx.durable.enabled:
            self._runner._cached_durable_config = self._runner.ctx.durable
            return self._runner._cached_durable_config
        if (
            self._runner.parent
            and self._runner.parent.ctx.durable
            and self._runner.parent.ctx.durable.enabled
        ):
            self._runner._cached_durable_config = self._runner.parent.ctx.durable
            return self._runner._cached_durable_config
        self._runner._cached_durable_config = None
        return None

    def checkpoint_id(self) -> str:
        parent_id = (
            self._runner.parent._checkpoint_id() if self._runner.parent else "workflow"
        )
        if hasattr(self._runner.model, "jid") and hasattr(self._runner.model, "step_index"):
            local_id = f"job:{self._runner.model.jid}:{self._runner.model.step_index}"
        elif hasattr(self._runner.model, "jid"):
            local_id = f"job:{self._runner.model.jid}"
        elif hasattr(self._runner.model, "name"):
            local_id = f"{self._runner.__class__.__name__}:{self._runner.model.name}"
        else:
            local_id = f"{self._runner.__class__.__name__}:{self._runner.run_id}"
        return f"{parent_id}/{local_id}"

    def checkpoint_status(self) -> str:
        status = self._runner.status
        if status == RunnerStatus.FINISHED:
            status = RunnerStatus.COMPLETED
        return status.value

    async def auto_commit_push(self) -> None:
        """Auto-commit and/or push output directory after workflow completion."""
        if self._runner.parent is not None:
            return
        config = self.durable_config()
        if not config:
            return
        if not (config.auto_commit or config.auto_push):
            return
        if not self._runner.ctx.output_path:
            return
        if not self._runner._state_machine.is_terminal:
            return

        try:
            await commit_and_push(
                self._runner.ctx.output_path,
                do_commit=config.auto_commit,
                do_push=config.auto_push,
                message=(
                    f"checkpoint: {getattr(self._runner.model, 'name', 'workflow')} "
                    f"[{self._runner.status.value}]"
                ),
            )
        except Exception as exc:
            self._runner._log_warning(f"auto-commit/push failed: {exc}")
