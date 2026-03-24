"""Runner models and enums"""

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ofx.models.config import DurableRunConfig
from ofx.settings import DEFAULT_WORKFLOWS_DIRS
from ofx.utils.env import populate_env


class RunnerStatus(Enum):
    """Status of a runner execution"""

    IDLE = "idle"
    RUNNING = "running"
    FINISHED = "finished"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class RunContext(BaseModel):
    """Execution context for runners"""

    inputs: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)
    envs: dict[str, Any] = Field(default_factory=populate_env)
    output_path: Path | None = Field(
        default=None, description="Path to store runner outputs"
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


class RunResult(BaseModel):
    """Result of a runner execution"""

    name: str = Field(...)
    run_id: str = Field(...)
    status: RunnerStatus
    error: str | None = None
    outputs: dict[str, Any] = Field(default_factory=dict)


class ConditionNotMetError(RuntimeError):
    """Raised when a job/step run_if condition evaluates to false."""
