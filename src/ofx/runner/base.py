import uuid
from enum import Enum
from pathlib import Path

from ofx.models import DefaultConfig
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional


class RunnerStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELED = "canceled"
    COMPLETED = "completed"
    FAILED = "failed"


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
    defaults: DefaultConfig = Field(
        default_factory=DefaultConfig,
        description="Default configuration for the workflow run",
    )
    output_path: Path = Field(
        default=Path.cwd() / "out",
        description="Path to store output files",
    )


class BaseRunner:
    _manager = None

    def __init__(self, name: str, ctx: RunContext):
        self._id = f"{name}-{str(uuid.uuid4())}"
        self._status = RunnerStatus.IDLE
        self._error = None
        self._success = False
        self._progress = 0.0
        self._result = {}
        self._ctx = ctx

    async def run(self):
        """Run the workflow and return the result."""
        try:
            await self._pre_run()
            self._status = RunnerStatus.RUNNING
            await self._do_run()
            self._status = RunnerStatus.COMPLETED
            self._success = True
            self._progress = 1.0
        except Exception as e:
            self._status = RunnerStatus.FAILED
            self._error = str(e)
        await self._post_run()
        return self._result

    async def _do_run(self):
        raise NotImplementedError("Subclasses should implement this method.")

    async def _pre_run(self):
        raise NotImplementedError("Subclasses should implement this method.")

    async def _post_run(self):
        raise NotImplementedError("Subclasses should implement this method.")

    def attach_manager(self, manager):
        self._manager = manager

    @property
    def status(self) -> RunnerStatus:
        return self._status

    @property
    def is_finished(self) -> bool:
        return self._status in {
            RunnerStatus.COMPLETED,
            RunnerStatus.FAILED,
            RunnerStatus.CANCELED,
        }

    @property
    def run_id(self) -> str:
        return self._id

    def get_result(self) -> Dict[str, Any]:
        """
        Get the result of the workflow run.
        """
        return self._result
