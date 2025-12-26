from typing import Dict, Any, TYPE_CHECKING

from ofx.runner.core.models import RunnerStatus

if TYPE_CHECKING:
    from ofx.runner.runners import JobRunner


class JobRegistry:
    def __init__(self):
        self._registry: Dict[str, Dict[str, Any]] = {}

    def register_job(self, job_id: str, job_data: Dict[str, Any]):
        self._registry[job_id] = job_data

    def update_job(self, job_id: str, updates: Dict[str, Any]):
        if job_id in self._registry:
            self._registry[job_id].update(updates)
        else:
            self._registry[job_id] = updates

    def get_job(self, job_id: str) -> Dict[str, Any] | None:
        return self._registry.get(job_id)

    def get_job_status(self, job_id: str) -> RunnerStatus | None:
        job = self._registry.get(job_id, {})
        return job.get("status")

    def get_all_jobs(self) -> Dict[str, Dict[str, Any]]:
        return self._registry

    def set_job_runner(self, job_id: str, runner: "JobRunner"):
        if job_id not in self._registry:
            self._registry[job_id] = {}
        self._registry[job_id]["runner"] = runner

    def get_job_runner(self, job_id: str) -> "JobRunner":
        job = self._registry.get(job_id, {})
        runner = job.get("runner")
        if not runner:
            raise RuntimeError(f"Runner for job '{job_id}' not found in registry.")
        return runner