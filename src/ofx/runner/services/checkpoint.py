"""Durable checkpoint lifecycle helpers for runners."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ofx.runner.durable import (
    clean_all_checkpoints,
    clean_checkpoints,
    clean_stale_checkpoints,
    get_checkpoint,
    list_checkpoints,
    write_checkpoint,
)
from ofx.runner.context import RunnerStatus
from ofx.runner.durable_git import commit_and_push
from ofx.runner.metadata import ModelContext
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
        output_path = self._runner.ctx.output_path
        if not config or not output_path:
            return

        model_context = ModelContext.from_model(self._runner.model)
        checkpoint_id = self.checkpoint_id()
        payload = {
            "run_id": self._runner.run_id,
            "checkpoint_id": checkpoint_id,
            "status": status,
            "runner_type": self._runner.__class__.__name__,
            "model_type": type(self._runner.model).__name__,
            "name": model_context.name,
            "parent_run_id": (
                self._runner.parent.run_id if self._runner.parent else None
            ),
            "started_at": self._runner.started_at,
            "finished_at": self._runner.finished_at,
            "duration_ms": self._runner.duration_ms(),
            "error": self._runner._error,
            "job_id": model_context.jid,
            "step_index": model_context.step_index,
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
            output_path,
            config,
            checkpoint_id,
            payload,
        )

    async def restore_from_checkpoint(self) -> bool:
        config = self.durable_config()
        output_path = self._runner.ctx.output_path
        if not config or not output_path or not config.resume:
            return False

        checkpoint_id = self.checkpoint_id()
        checkpoint = await get_checkpoint(
            output_path,
            config,
            checkpoint_id,
        )
        if not (checkpoint and checkpoint.get("status") == "completed"):
            return False

        self._runner._error = checkpoint.get("error")
        self._runner._started_at_utc = checkpoint.get("started_at")
        self._runner._finished_at_utc = checkpoint.get("finished_at")
        self._runner._state_machine.set_state(RunnerStatus.COMPLETED)
        if "outputs" in checkpoint:
            await self._runner.reg_set(
                RunnerRegistryKeys.OUTPUTS,
                checkpoint.get("outputs", {}),
            )
        return True

    def durable_config(self):
        """Return the durable config, cached after first lookup."""
        if self._runner._cached_durable_config is not None:
            return self._runner._cached_durable_config

        config = self._runner.ctx.durable
        if not (config and config.enabled):
            config = None

        if config is None and self._runner.parent is not None:
            parent_config = self._runner.parent.ctx.durable
            if parent_config and parent_config.enabled:
                config = parent_config

        self._runner._cached_durable_config = config
        return config

    def checkpoint_id(self) -> str:
        if self._runner.parent is None:
            parent_id = "workflow"
        else:
            parent_lifecycle = getattr(self._runner.parent, "_lifecycle", None)
            if parent_lifecycle is not None:
                parent_id = parent_lifecycle.checkpoint_id()
            elif hasattr(self._runner.parent, "_checkpoint_id"):
                parent_id = self._runner.parent._checkpoint_id()
            else:
                parent_id = CheckpointManager(self._runner.parent).checkpoint_id()

        model_context = ModelContext.from_model(self._runner.model)
        if model_context.jid is not None:
            local_id = (
                f"job:{model_context.jid}:{model_context.step_index}"
                if model_context.step_index is not None
                else f"job:{model_context.jid}"
            )
        elif model_context.name is not None:
            local_id = f"{self._runner.__class__.__name__}:{model_context.name}"
        else:
            local_id = f"{self._runner.__class__.__name__}:{self._runner.run_id}"

        return f"{parent_id}/{local_id}"

    async def auto_commit_push(self) -> None:
        """Auto-commit and/or push output directory after workflow completion."""
        config = self.durable_config()
        if not config:
            return
        if self._runner.parent is not None:
            return
        if not (config.auto_commit or config.auto_push):
            return
        if not self._runner.ctx.output_path:
            return
        if not self._runner._state_machine.is_terminal:
            return

        model_context = ModelContext.from_model(self._runner.model)
        message = (
            f"checkpoint: {model_context.name or 'workflow'} "
            f"[{self._runner.status.value}]"
        )

        try:
            await commit_and_push(
                self._runner.ctx.output_path,
                do_commit=config.auto_commit,
                do_push=config.auto_push,
                message=message,
            )
        except Exception as exc:
            self._runner._log_warning(f"auto-commit/push failed: {exc}")


__all__ = [
    "CheckpointManager",
    "clean_all_checkpoints",
    "clean_checkpoints",
    "clean_stale_checkpoints",
    "find_running_checkpoints",
    "get_checkpoint",
    "list_checkpoints",
    "write_checkpoint",
]
