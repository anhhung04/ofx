"""Job runners delegating orchestration to executor classes."""

from __future__ import annotations

from typing import Any

from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.context import (
    RunContext,
    context_copy,
    context_with_update,
    context_with_vars,
)
from ofx.runner.executors.job import JobExecutor
from ofx.runner.executors.matrix import MatrixExecutor
from ofx.runner.logging import bubble_context_log
from ofx.runner.runner import Runner

def build_indexed_job_context(
    runner,
    *,
    vars_update: dict[str, Any] | None = None,
    input_updates: dict[str, Any] | None = None,
) -> RunContext:
    """Build a child job context with shared strategy/input propagation."""
    child_context_factory = getattr(runner, "_child_context", None)
    job_ctx = (
        child_context_factory()
        if callable(child_context_factory)
        else context_copy(runner.ctx)
    )
    merged_vars: dict[str, Any] = {}
    if runner.model.strategy:
        merged_vars["strategy"] = runner.model.strategy.model_dump()
    if vars_update:
        merged_vars.update(vars_update)
    if merged_vars:
        job_ctx = context_with_vars(job_ctx, merged_vars)
    if input_updates:
        job_ctx = context_with_update(
            job_ctx,
            {"inputs": {**job_ctx.inputs, **input_updates}},
        )

    return job_ctx

def attach_indexed_job_runner(
    runner,
    *,
    ctx: RunContext,
    index: int,
    values: dict[str, Any],
    runner_cls,
    display_name: str | None = None,
    parent=None,
    **runner_kwargs,
):
    """Create, register, and return an indexed child job runner."""
    job_copy = runner.model.model_copy(
        deep=True,
        update={
            "name": display_name or f"[{runner.model.name or runner.model.jid}]{{{index}}}",
            "jid": f"{runner.model.jid}_{index}",
            "matrix_values": values,
            "matrix_index": index,
        },
    )
    child_runner = runner_cls(
        job_copy,
        ctx,
        parent=parent or runner.parent,
        **runner_kwargs,
    )
    runner._runners[job_copy.jid] = child_runner
    return job_copy, child_runner

class JobRunner(Runner[Job]):
    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: Runner[Workflow],
        executor: JobExecutor | None = None,
    ):
        super().__init__(
            job,
            ctx,
            parent,
            parent.registry,
            executor=executor or JobExecutor(),
        )

    def _produce_log(self, message: Any) -> str:
        return bubble_context_log(self.parent, message, model_jid=self.model.jid)

class MatrixJobRunner(JobRunner):
    """Runner for jobs with matrix strategy, handling multiple combinations."""

    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: Runner[Workflow],
        executor: MatrixExecutor | None = None,
    ):
        super().__init__(job, ctx, parent, executor=executor or MatrixExecutor())
        self.name = f"Matrix{self.name}"

__all__ = [
    "JobRunner",
    "MatrixJobRunner",
    "build_indexed_job_context",
    "attach_indexed_job_runner",
]
