"""Runner context models and immutable context update helpers."""

from __future__ import annotations

import copy
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ofx.models.config import DurableRunConfig
from ofx.settings import get_workflow_search_dirs
from ofx.utils.env import populate_env

class RunnerStatus(Enum):
    """Status of a runner execution."""

    IDLE = "idle"
    RUNNING = "running"
    FINISHED = "finished"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

def normalize_runner_status(status: RunnerStatus) -> RunnerStatus:
    """Map transient terminal runner states to their external representation."""
    return RunnerStatus.COMPLETED if status == RunnerStatus.FINISHED else status

def normalized_runner_status_value(status: RunnerStatus) -> str:
    """Return the external string value for a runner status."""
    return normalize_runner_status(status).value

class RunContext(BaseModel):
    """Execution context shared by runners and executors."""

    inputs: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)
    envs: dict[str, Any] = Field(default_factory=populate_env)
    output_path: Path | None = Field(
        default=None,
        description="Path to store runner outputs",
    )
    workflow_dir: Path | None = Field(
        default=None,
        description="Directory of the currently executing workflow for relative assets.",
    )
    vars: dict[str, Any] = Field(default_factory=dict)
    allow_interactive: bool = Field(
        default=False,
        description="Whether interactive mode is allowed (single job in stage)",
    )
    workflow_dirs: list[Path] = Field(
        default_factory=get_workflow_search_dirs,
        description="Directories to search for workflow files",
    )
    durable: DurableRunConfig | None = Field(
        default=None,
        description="Durable execution configuration",
    )
    event_sink_path: Path | None = Field(
        default=None,
        description="Optional NDJSON path for structured runner lifecycle events",
    )

    def __repr__(self) -> str:
        secret_keys = list(self.secrets.keys()) if self.secrets else []
        return (
            f"RunContext(inputs={list(self.inputs.keys())}, "
            f"secrets=[{len(secret_keys)} key(s)], "
            f"output_path={self.output_path!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()

class RunResult(BaseModel):
    """Result of a runner execution."""

    name: str = Field(...)
    run_id: str = Field(...)
    status: RunnerStatus
    error: str | None = None
    outputs: dict[str, Any] = Field(default_factory=dict)

    def __repr__(self) -> str:
        err = f", error={self.error!r}" if self.error else ""
        return f"RunResult({self.name!r}, status={self.status.value}{err})"

    def __str__(self) -> str:
        return self.__repr__()

class ConditionNotMetError(RuntimeError):
    """Raised when a job or step condition evaluates to false."""

def context_with_env(ctx: RunContext, env: dict[str, Any]) -> RunContext:
    """Return a context copy with merged environment updates."""
    return _context_with_merged_field_update(ctx, "envs", env)

def context_with_secrets(ctx: RunContext, secrets: dict[str, Any]) -> RunContext:
    """Return a context copy with merged secret updates."""
    return _context_with_merged_field_update(ctx, "secrets", secrets)

def context_with_vars(ctx: RunContext, vars_update: dict[str, Any]) -> RunContext:
    """Return a context copy with merged variable updates."""
    return _context_with_merged_field_update(ctx, "vars", vars_update)

def context_with_update(ctx: RunContext, update: dict[str, Any]) -> RunContext:
    """Return a context copy with arbitrary field updates."""
    return context_copy(ctx, update)

def context_copy(
    ctx: RunContext,
    update: dict[str, Any] | None = None,
    *,
    deep: bool = True,
) -> RunContext:
    """Return a copied context, optionally applying field replacements."""
    return ctx.model_copy(update=update or {}, deep=deep)

def _context_with_merged_dict_updates(
    ctx: RunContext,
    **updates_by_field: dict[str, Any],
) -> RunContext:
    merged_updates = {
        field: copy.deepcopy(getattr(ctx, field)) | updates
        for field, updates in updates_by_field.items()
    }
    return ctx.model_copy(update=merged_updates)

def _context_with_merged_field_update(
    ctx: RunContext,
    field: str,
    updates: dict[str, Any],
) -> RunContext:
    return _context_with_merged_dict_updates(ctx, **{field: updates})

__all__ = [
    "ConditionNotMetError",
    "context_copy",
    "context_with_env",
    "context_with_secrets",
    "context_with_update",
    "context_with_vars",
    "normalized_runner_status_value",
    "normalize_runner_status",
    "RunContext",
    "RunResult",
    "RunnerStatus",
]
