"""Runner models and enums"""
import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


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
    inputs: Dict[str, Any] = Field(default_factory=dict)
    secrets: Dict[str, Any] = Field(default_factory=dict)
    envs: Dict[str, Any] = Field(default_factory=lambda: os.environ.copy())
    output_path: Path = Field(default=Path.cwd() / "out")
    vars: Dict[str, Any] = Field(default_factory=dict)


class RunResult(BaseModel):
    """Result of a runner execution"""
    status: RunnerStatus
    error: Optional[str] = None
    outputs: Dict[str, Any] = Field(default_factory=dict)
    name: str = Field(...)
    run_id: str = Field(...)
    metadata: Dict[str, Any] = Field(default_factory=dict)
