from enum import Enum
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional


class RunnerStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

class RunContext(BaseModel):
    inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Inputs for the workflow run, can be used to pass parameters",
    )
    secrets: Dict[str, Any] = Field(
        default_factory=dict,
        description="Secrets for the workflow run, can be used to pass sensitive information",
    )
    envs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Environment variables for the workflow run",
    )
    output_path: Path = Field(
        default=Path.cwd() / "out",
        description="Path to store output files",
    )
    vars: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context variables for the workflow run",
    )


class RunResult(BaseModel):
    status: RunnerStatus
    error: Optional[str] = None
    outputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Outputs produced by the run",
    )
    name: str = Field(..., description="Name of the run")
    run_id: str = Field(..., description="Unique identifier for the run")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for the run",
    )
