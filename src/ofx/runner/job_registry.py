import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ofx.runner.runner import RunnerStatus


@dataclass
class JobEntry:
    job_id: str
    name: str
    status: RunnerStatus = RunnerStatus.IDLE

    metadata: Dict[str, Any] = field(default_factory=dict)

    runner: Optional[Any] = None

    result: Optional[bool] = None
    error: Optional[Exception] = None
    outputs: Dict[str, Any] = field(default_factory=dict)
    steps: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "status": (
                self.status.value
                if isinstance(self.status, RunnerStatus)
                else self.status
            ),
            "result": self.result,
            "outputs": self.outputs,
            "steps": self.steps,
            **self.metadata,
        }

    @property
    def is_running(self) -> bool:
        return self.status == RunnerStatus.RUNNING

    @property
    def is_completed(self) -> bool:
        return self.status == RunnerStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        return self.status == RunnerStatus.FAILED

    @property
    def processed_steps(self) -> int:
        if self.runner and hasattr(self.runner, "processed_steps"):
            return self.runner.processed_steps
        return 0


class JobRegistry:
    def __init__(self):
        self._entries: Dict[str, JobEntry] = {}
        self._lock = threading.Lock()

    def register(
        self, job_id: str, name: str, metadata: Optional[Dict[str, Any]] = None
    ) -> JobEntry:
        with self._lock:
            entry = JobEntry(
                job_id=job_id,
                name=name,
                metadata=metadata or {},
            )
            self._entries[job_id] = entry
            return entry

    def set_runner(self, job_id: str, runner: Any) -> None:
        with self._lock:
            if job_id in self._entries:
                self._entries[job_id].runner = runner
                self._entries[job_id].status = RunnerStatus.RUNNING

    def set_result(self, job_id: str, result: bool) -> None:
        with self._lock:
            if job_id in self._entries:
                self._entries[job_id].result = result

    def set_error(self, job_id: str, error: Exception) -> None:
        with self._lock:
            if job_id in self._entries:
                self._entries[job_id].error = error
                self._entries[job_id].result = False
                self._entries[job_id].status = RunnerStatus.FAILED

    def update_outputs(
        self, job_id: str, outputs: Dict[str, Any], steps: Dict[str, Any]
    ) -> None:
        with self._lock:
            if job_id in self._entries:
                self._entries[job_id].outputs.update(outputs)
                self._entries[job_id].steps.update(steps)
                if self._entries[job_id].result:
                    self._entries[job_id].status = RunnerStatus.COMPLETED

    def get_entry(self, job_id: str) -> Optional[JobEntry]:
        with self._lock:
            return self._entries.get(job_id)

    def get_runner(self, job_id: str) -> Optional[Any]:
        with self._lock:
            entry = self._entries.get(job_id)
            return entry.runner if entry else None

    def get_status(self, job_id: str) -> Optional[RunnerStatus]:
        with self._lock:
            entry = self._entries.get(job_id)
            return entry.status if entry else None

    def get_result(self, job_id: str) -> Optional[bool]:
        with self._lock:
            entry = self._entries.get(job_id)
            return entry.result if entry else None

    def get_error(self, job_id: str) -> Optional[Exception]:
        with self._lock:
            entry = self._entries.get(job_id)
            return entry.error if entry else None

    def has_error(self, job_id: str) -> bool:
        with self._lock:
            entry = self._entries.get(job_id)
            return entry.error is not None if entry else False

    def get_processed_steps(self, job_ids: list[str]) -> int:
        with self._lock:
            total = 0
            for job_id in job_ids:
                entry = self._entries.get(job_id)
                if entry:
                    total += entry.processed_steps
            return total

    def exists(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._entries

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {job_id: entry.to_dict() for job_id, entry in self._entries.items()}

    def get_all_entries(self) -> Dict[str, JobEntry]:
        with self._lock:
            return dict(self._entries)

    def all_completed(self) -> bool:
        with self._lock:
            return all(
                entry.status == RunnerStatus.COMPLETED
                for entry in self._entries.values()
            )

    def get_job_statuses(self) -> list[tuple[str, str]]:
        with self._lock:
            return [
                (
                    entry.name,
                    (
                        entry.status.value
                        if isinstance(entry.status, RunnerStatus)
                        else entry.status
                    ),
                )
                for entry in self._entries.values()
            ]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __contains__(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._entries

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
