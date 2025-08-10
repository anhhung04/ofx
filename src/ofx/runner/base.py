import uuid
from enum import Enum
from typing import Dict, Any


class RunnerStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELED = "canceled"
    COMPLETED = "completed"
    FAILED = "failed"


class BaseRunner:
    _manager = None

    def __init__(self, name: str):
        self._status = RunnerStatus.IDLE
        self._result = {}
        self._error = None
        self._id = f"{name}-{str(uuid.uuid4())}"

    async def run(self) -> Dict[str, Any]:
        """Run the workflow and return the result."""
        await self._pre_run()
        self._status = RunnerStatus.RUNNING
        try:
            await self._do_run()
            self._status = RunnerStatus.COMPLETED
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

    def _update_progress(self) -> bool:
        """Update the progress of the runner."""
        raise NotImplementedError("Subclasses should implement this method.")

    def attach_manager(self, manager):
        self._manager = manager

    @property
    def status(self) -> RunnerStatus:
        return self._status

    @property
    def is_finished(self) -> bool:
        return self._status in {RunnerStatus.COMPLETED, RunnerStatus.FAILED}

    @property
    def run_id(self) -> str:
        return self._id
