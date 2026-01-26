"""Workflow scheduling utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ofx.models.job import Job
from ofx.utils.scheduling import find_parallel_schedule


@dataclass(frozen=True)
class WorkflowSchedule:
    staged_jobs: dict[str, Job]
    schedule: list[list[str]]


class WorkflowScheduler:
    """Builds an execution schedule for workflow jobs."""

    def __init__(self, jobs: dict[str, Job]):
        self._jobs = jobs

    def plan(self) -> WorkflowSchedule:
        dependencies = [
            (dep, job_id)
            for job_id, job in self._jobs.items()
            for dep in job.needs
            if dep
        ]
        schedule = find_parallel_schedule(list(self._jobs.keys()), dependencies)
        return WorkflowSchedule(staged_jobs=self._jobs, schedule=schedule)

    @staticmethod
    def dependencies(jobs: dict[str, Job]) -> list[tuple[str, str]]:
        return [
            (dep, job_id)
            for job_id, job in jobs.items()
            for dep in job.needs
            if dep
        ]

    @staticmethod
    def job_ids(jobs: dict[str, Job]) -> Iterable[str]:
        return jobs.keys()
