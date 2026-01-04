"""Runner models and enums"""
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ofx.utils.misc import populate_env


class RunnerStatus(Enum):
    """Status of a runner execution"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class RunType(Enum):
    """Type of step execution"""
    SCRIPT = "script"
    COMMAND = "command"
    WORKFLOW = "workflow"

class RunContext(BaseModel):
    """Execution context for runners"""
    inputs: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)
    envs: dict[str, Any] = Field(default_factory=populate_env)
    output_path: Path = Field(default=Path.cwd() / "out")
    vars: dict[str, Any] = Field(default_factory=dict)
    allow_interactive: bool = Field(default=False, description="Whether interactive mode is allowed (single job in stage)")
    workflow_dirs: list[Path] = Field(default_factory=list, description="Directories to search for workflow files")


class RunResult(BaseModel):
    """Result of a runner execution"""
    status: RunnerStatus
    error: str | None = None
    outputs: dict[str, Any] = Field(default_factory=dict)
    name: str = Field(...)
    run_id: str = Field(...)
    metadata: dict[str, Any] = Field(default_factory=dict)
