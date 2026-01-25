"""Execution summary reporter for workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ofx.runner.core import RunnerStatus
from ofx.runner.execution.job import JobRunner
from ofx.runner.execution.step import StepRunner


@dataclass
class ExecutionSummary:
    workflow_name: str
    status: str
    total_jobs: int
    failed_jobs: int
    total_steps: int
    failed_steps: int
    jobs: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_name": self.workflow_name,
            "status": self.status,
            "total_jobs": self.total_jobs,
            "failed_jobs": self.failed_jobs,
            "total_steps": self.total_steps,
            "failed_steps": self.failed_steps,
            "jobs": self.jobs,
        }


class ExecutionSummaryReporter:
    """Aggregates workflow/job/step execution data."""

    def __init__(self, workflow_runner):
        self._workflow = workflow_runner

    async def build(self) -> ExecutionSummary:
        jobs_summary: list[dict[str, Any]] = []
        total_steps = 0
        failed_steps = 0
        failed_jobs = 0

        for job_id, runner in self._workflow.runners.items():
            if not isinstance(runner, JobRunner):
                continue
            job_exec = await runner.reg_get("execution")
            if not job_exec:
                job_exec = {
                    "jid": job_id,
                    "name": runner.model.name,
                    "status": runner.status.value,
                    "error": runner._error,
                    "total_steps": len(runner.model.steps),
                    "failed_steps": [],
                    "steps": [],
                }
            jobs_summary.append(job_exec)
            total_steps += job_exec.get("total_steps", 0)
            if job_exec.get("failed_steps"):
                failed_steps += len(job_exec.get("failed_steps", []))
            elif job_exec.get("steps"):
                failed_steps += sum(
                    1
                    for step in job_exec.get("steps", [])
                    if step.get("status") == RunnerStatus.FAILED.value
                )
            if runner.status == RunnerStatus.FAILED:
                failed_jobs += 1

        status = self._workflow.status.value
        return ExecutionSummary(
            workflow_name=self._workflow.model.name,
            status=status,
            total_jobs=len(self._workflow.runners),
            failed_jobs=failed_jobs,
            total_steps=total_steps,
            failed_steps=failed_steps,
            jobs=jobs_summary,
        )

    async def build_unified(self) -> dict[str, Any]:
        jobs: list[dict[str, Any]] = []
        total_steps = 0
        failed_steps = 0
        failed_jobs = 0

        for job_id, runner in self._workflow.runners.items():
            if not isinstance(runner, JobRunner):
                continue
            job_exec = await runner.reg_get("execution")
            steps: list[dict[str, Any]] = []
            if job_exec and job_exec.get("steps"):
                steps = [
                    {
                        "step_index": step.get("step_index"),
                        "name": step.get("name"),
                        "status": step.get("status"),
                        "error": step.get("error"),
                    }
                    for step in job_exec.get("steps", [])
                ]
            else:
                for step_runner in runner._runners.values():
                    if isinstance(step_runner, StepRunner):
                        step_result = await step_runner.get_result()
                        steps.append(
                            {
                                "step_index": step_runner.model.step_index,
                                "name": step_runner.model.name,
                                "status": step_result.status.value,
                                "error": step_result.error,
                            }
                        )
            total_steps += job_exec.get("total_steps", len(steps))
            failed_steps += sum(
                1 for step in steps if step.get("status") == RunnerStatus.FAILED.value
            )
            if runner.status == RunnerStatus.FAILED:
                failed_jobs += 1
            jobs.append(
                {
                    "jid": job_id,
                    "name": runner.model.name,
                    "status": runner.status.value,
                    "error": runner._error,
                    "steps": steps,
                }
            )

        return {
            "workflow_name": self._workflow.model.name,
            "status": self._workflow.status.value,
            "total_jobs": len(self._workflow.runners),
            "failed_jobs": failed_jobs,
            "total_steps": total_steps,
            "failed_steps": failed_steps,
            "jobs": jobs,
        }
