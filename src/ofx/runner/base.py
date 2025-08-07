from enum import Enum
import uuid


class RunnerStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class BaseRunner:
    def __init__(self, name: str):
        self._status = RunnerStatus.IDLE
        self._result = None
        self._error = None
        self._progress = 0.0
        self._id = f"{name}-{str(uuid.uuid4())}"

    async def run(self):
        raise NotImplementedError("Subclasses should implement this method.")

    async def pre_run(self):
        pass

    async def post_run(self):
        pass

    @property
    def status(self) -> RunnerStatus:
        return self._status

    @property
    def is_finished(self) -> bool:
        return (
            self._status in {RunnerStatus.COMPLETED, RunnerStatus.FAILED}
            or self._progress >= 1.0
        )

    @property
    def run_id(self) -> str:
        return self._id
