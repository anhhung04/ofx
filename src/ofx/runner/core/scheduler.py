import logging
from typing import Dict, Any

from ofx.models.workflow import Workflow
from ofx.settings import settings
from ofx.utils.misc import find_parallel_schedule

logger = logging.getLogger(settings.app_branding)


class JobScheduler:
    def __init__(self, workflow: Workflow):
        self._workflow = workflow
        self._schedule = []
        self._total_steps = 0

    def plan_execution(self) -> tuple[list[set[str]], int]:
        jobs = self._workflow.jobs
        job_keys = list(jobs.keys())
        deps_relationships = []
        
        for job_id, job in jobs.items():
            if job.needs:
                if isinstance(job.needs, str):
                    job.needs = [job.needs]
                for dep in job.needs:
                    if dep and dep not in job_keys:
                        raise ValueError(
                            f"Job '{job.name}' depends on '{dep}', which is not defined in the workflow."
                        )
                    deps_relationships.append((dep, job_id))
        
        self._schedule = find_parallel_schedule(job_keys, deps_relationships)
        self._total_steps = sum(
            sum(len(jobs[job_id].steps) for job_id in stage) for stage in self._schedule
        )
        
        logger.debug(f"Execution stages: {self._schedule}")
        return self._schedule, self._total_steps

    @property
    def schedule(self) -> list[set[str]]:
        return self._schedule

    @property
    def total_steps(self) -> int:
        return self._total_steps
