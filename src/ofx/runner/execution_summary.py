"""Execution summary reporter for workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ofx.runner.context import RunnerStatus, normalized_runner_status_value
from ofx.runner.metadata import ModelContext
from ofx.runner.runner_refs import runner_leaf_descendants

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
        return asdict(self)

class ExecutionSummaryReporter:
    """Aggregates workflow/job/step execution data."""

    def __init__(self, workflow_runner):
        self._workflow = workflow_runner
        self._source_jobs: list[dict[str, Any]] | None = None

    async def _load_job_summaries(self) -> list[dict[str, Any]]:
        if self._source_jobs is None:
            self._source_jobs = await self._job_summaries()
        return self._source_jobs

    async def _job_summaries(self) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for job_id, runner in self._workflow.runners.items():
            model_context = ModelContext.from_model(getattr(runner, "model", None))
            if model_context.jid is None or model_context.step_index is not None:
                continue
            job_exec = await runner.reg_get("execution")
            if job_exec:
                summaries.append(job_exec)
                continue

            step_summaries: list[dict[str, Any]] = []
            for child in runner_leaf_descendants(runner):
                step_context = ModelContext.from_model(getattr(child, "model", None))
                if step_context.step_index is None:
                    continue
                try:
                    result = await child.get_result()
                    status = normalized_runner_status_value(result.status)
                    error = result.error
                except Exception:
                    status = normalized_runner_status_value(getattr(child, "status", None))
                    error = getattr(child, "_error", None)
                step_summaries.append(
                    {
                        "step_index": step_context.step_index,
                        "name": step_context.name,
                        "status": status,
                        "error": error,
                        "duration_ms": child.duration_ms(),
                    }
                )

            model_steps = getattr(getattr(runner, "model", None), "steps", []) or []
            summaries.append(
                {
                    "jid": job_id,
                    "name": model_context.name,
                    "status": normalized_runner_status_value(
                        getattr(runner, "status", None)
                    ),
                    "error": getattr(runner, "_error", None),
                    "total_steps": len(step_summaries) or len(model_steps),
                    "failed_steps": [
                        step_index
                        for step in step_summaries
                        for step_index in [step.get("step_index")]
                        if isinstance(step_index, int)
                        and step.get("status") == RunnerStatus.FAILED.value
                    ],
                    "steps": step_summaries,
                    "duration_ms": runner.duration_ms(),
                }
            )
        return summaries

    def _workflow_summary_payload(
        self,
        source_jobs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        total_steps = 0
        failed_steps = 0
        for job in source_jobs:
            job_steps = job.get("steps", [])
            job_total_steps = job.get("total_steps")
            total_steps += (
                job_total_steps
                if isinstance(job_total_steps, int)
                else len(job_steps) if isinstance(job_steps, list) else 0
            )
            job_failed_steps = job.get("failed_steps")
            if isinstance(job_failed_steps, list) and job_failed_steps:
                failed_steps += len(job_failed_steps)
            elif isinstance(job_steps, list):
                failed_steps += sum(
                    1 for step in job_steps if step.get("status") == RunnerStatus.FAILED.value
                )

        return {
            "workflow_name": self._workflow.model.name,
            "status": normalized_runner_status_value(self._workflow.status),
            "total_jobs": len(source_jobs),
            "failed_jobs": sum(
                1 for job in source_jobs if job.get("status") == RunnerStatus.FAILED.value
            ),
            "total_steps": total_steps,
            "failed_steps": failed_steps,
        }

    async def build(self) -> ExecutionSummary:
        jobs_summary = await self._load_job_summaries()
        payload = self._workflow_summary_payload(jobs_summary)
        payload["jobs"] = jobs_summary
        return ExecutionSummary(**payload)

    async def build_unified(self) -> dict[str, Any]:
        job_summaries = await self._load_job_summaries()
        jobs = [
            {
                "jid": job.get("jid"),
                "name": job.get("name"),
                "status": job.get("status"),
                "error": job.get("error"),
                "duration_ms": job.get("duration_ms"),
                "steps": [
                    {
                        "step_index": step.get("step_index"),
                        "name": step.get("name"),
                        "status": step.get("status", ""),
                        "error": step.get("error"),
                        "duration_ms": step.get("duration_ms"),
                    }
                    for step in job.get("steps", [])
                ]
                if isinstance(job.get("steps"), list)
                else [],
            }
            for job in job_summaries
        ]
        payload = self._workflow_summary_payload(job_summaries)
        payload["jobs"] = jobs
        return payload
