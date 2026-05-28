"""Job runners delegating orchestration to executor classes."""

from __future__ import annotations

from typing import Any

from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.context import RunContext
from ofx.runner.executors.job import JobExecutor
from ofx.runner.executors.matrix import MatrixExecutor
from ofx.runner.logging import bubble_context_log
from ofx.runner.runner import BaseRunner


def format_job_log(parent: BaseRunner[Workflow], job: Job, message: Any) -> str:
    """Format and bubble a local job runner log message."""
    return bubble_context_log(parent, message, model_jid=job.jid)


def clone_indexed_job(
    job: Job,
    index: int,
    values: dict[str, Any],
    *,
    display_name: str | None = None,
) -> Job:
    """Clone a job for a matrix or fleet child execution."""
    new_jid = f"{job.jid}_{index}"
    child_name = display_name or f"[{job.name or job.jid}]{{{index}}}"
    return job.model_copy(
        deep=True,
        update={
            "name": child_name,
            "jid": new_jid,
            "matrix_values": values,
            "matrix_index": index,
        },
    )


class JobRunner(BaseRunner[Job]):
    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
        executor: JobExecutor | None = None,
    ):
        job_executor = executor or JobExecutor()
        super().__init__(
            job,
            ctx,
            parent,
            parent.registry,
            executor=job_executor,
        )

    @property
    def total_steps(self) -> int:
        return len(self.model.steps)

    def _produce_log(self, message: Any) -> str:
        return format_job_log(self.parent, self.model, message)


class MatrixJobRunner(BaseRunner[Job]):
    """Runner for jobs with matrix strategy, handling multiple combinations."""

    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
        executor: MatrixExecutor | None = None,
    ):
        matrix_executor = executor or MatrixExecutor()
        super().__init__(job, ctx, parent, executor=matrix_executor)
        self.name = f"Matrix{self.name}"

    def _produce_log(self, message: Any) -> str:
        return format_job_log(self.parent, self.model, message)


__all__ = ["JobRunner", "MatrixJobRunner", "clone_indexed_job", "format_job_log"]
