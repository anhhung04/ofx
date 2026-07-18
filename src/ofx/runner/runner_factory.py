"""Runner factory for selecting the appropriate job runner implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ofx.models.job import Job

def job_runner_class(job: Job):
    """Return the runner class appropriate for the given job configuration."""
    has_cloud = job.cloud is not None
    has_matrix = bool(job.strategy and job.strategy.matrix)
    has_fleet = bool(job.strategy and job.strategy.fleet)

    if has_cloud and has_fleet:
        from ofx.runner.cloud_fleet import CloudFleetRunner

        return CloudFleetRunner

    if has_cloud and has_matrix:
        from ofx.runner.cloud_matrix import CloudMatrixJobRunner

        return CloudMatrixJobRunner

    if has_cloud:
        from ofx.runner.cloud_job import CloudJobRunner

        return CloudJobRunner

    if has_matrix:
        from ofx.runner.job import MatrixJobRunner

        return MatrixJobRunner

    from ofx.runner.job import JobRunner

    return JobRunner

__all__ = ["job_runner_class"]
