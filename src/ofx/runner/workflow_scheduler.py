"""Workflow scheduling utilities."""

from __future__ import annotations

from dataclasses import dataclass

from ofx.models.job import Job
from ofx.utils.scheduling import find_parallel_schedule


@dataclass(frozen=True)
class WorkflowSchedule:
    """Topologically sorted execution plan for workflow jobs."""

    staged_jobs: dict[str, Job]
    schedule: list[list[str]]


class WorkflowScheduler:
    """Builds an execution schedule for workflow jobs."""

    def __init__(self, jobs: dict[str, Job]):
        self._jobs = jobs

    def plan(self) -> WorkflowSchedule:
        """Build the parallel execution schedule from job dependency graph."""
        dependencies = [
            (dep, job_id)
            for job_id, job in self._jobs.items()
            for dep in job.needs
            if dep
        ]
        schedule = find_parallel_schedule(list(self._jobs.keys()), dependencies)
        return WorkflowSchedule(staged_jobs=self._jobs, schedule=schedule)
