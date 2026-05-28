"""Runner context models and immutable context update helpers."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ofx.models.config import DurableRunConfig
from ofx.settings import DEFAULT_WORKFLOWS_DIRS
from ofx.utils.env import populate_env


class RunnerStatus(Enum):
    """Status of a runner execution."""

    IDLE = "idle"
    RUNNING = "running"
    FINISHED = "finished"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


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
        default=DEFAULT_WORKFLOWS_DIRS,
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


@dataclass(frozen=True)
class RunnerContextBuilder:
    """Immutable helper for all runner context mutations."""

    base: RunContext

    def _copy_with_dict_updates(self, **updates_by_field: dict[str, Any]) -> RunContext:
        merged_updates: dict[str, Any] = {}
        for field, updates in updates_by_field.items():
            current = copy.deepcopy(getattr(self.base, field))
            current.update(updates)
            merged_updates[field] = current
        return self.base.model_copy(update=merged_updates)

    def with_env(self, env: dict[str, Any]) -> RunContext:
        return self._copy_with_dict_updates(envs=env)

    def with_inputs(self, inputs: dict[str, Any]) -> RunContext:
        return self._copy_with_dict_updates(inputs=inputs)

    def with_secrets(self, secrets: dict[str, Any]) -> RunContext:
        return self._copy_with_dict_updates(secrets=secrets)

    def with_vars(self, vars_update: dict[str, Any]) -> RunContext:
        return self._copy_with_dict_updates(vars=vars_update)

    def with_env_and_vars(
        self,
        env: dict[str, Any],
        vars_update: dict[str, Any],
    ) -> RunContext:
        return self._copy_with_dict_updates(envs=env, vars=vars_update)

    def with_update(self, update: dict[str, Any]) -> RunContext:
        return self.base.model_copy(update=update)


ContextBuilder = RunnerContextBuilder


def build_env_context(env: dict[str, Any]) -> RunContext:
    """Create an isolated run context that carries only environment values."""
    return RunnerContextBuilder(RunContext()).with_env(env)

__all__ = [
    "build_env_context",
    "ConditionNotMetError",
    "ContextBuilder",
    "RunContext",
    "RunResult",
    "RunnerContextBuilder",
    "RunnerStatus",
]
