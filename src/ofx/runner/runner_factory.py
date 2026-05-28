"""Runner factory for selecting the appropriate job runner implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ofx.runner.runner import BaseRunner

if TYPE_CHECKING:
    from ofx.models.job import Job
    from ofx.runner.context import RunContext


def create_job_runner(
    job: Job,
    ctx: RunContext,
    parent: BaseRunner,
) -> BaseRunner:
    """Create the correct runner for a job based on cloud, matrix, and fleet config."""
    has_cloud = getattr(job, "cloud", None)
    has_matrix = job.strategy and job.strategy.matrix
    has_fleet = job.strategy and job.strategy.fleet

    if has_cloud and has_fleet:
        from ofx.runner.cloud_fleet import CloudFleetRunner

        return CloudFleetRunner(job, ctx, parent=parent)

    if has_cloud and has_matrix:
        from ofx.runner.cloud_matrix import CloudMatrixJobRunner

        return CloudMatrixJobRunner(job, ctx, parent=parent)

    if has_cloud:
        from ofx.runner.cloud_job import CloudJobRunner

        return CloudJobRunner(job, ctx, parent=parent)

    if has_matrix:
        from ofx.runner.job import MatrixJobRunner

        return MatrixJobRunner(job, ctx, parent=parent)

    from ofx.runner.job import JobRunner

    return JobRunner(job, ctx, parent=parent)


__all__ = ["create_job_runner"]
