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
        self._success = False
        self._progress = 0.0

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
