"""Runner factory — selects the appropriate runner type for a job.

Centralises the runner-selection logic formerly inlined in
``WorkflowExecutionManager._build_stage_runners()``, applying the
Dependency Inversion Principle: callers depend on this factory
instead of importing four concrete runner classes directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ofx.runner.core import BaseRunner

if TYPE_CHECKING:
    from ofx.models.job import Job
    from ofx.runner.core import RunContext


def create_job_runner(
    job: Job,
    ctx: RunContext,
    parent: BaseRunner,
) -> BaseRunner:
    """Create the correct runner for *job* based on its cloud/matrix/fleet config.

    Returns one of:
    * ``JobRunner``              — local, no matrix
    * ``MatrixJobRunner``        — local + matrix
    * ``CloudJobRunner``         — cloud, no matrix, no fleet
    * ``CloudMatrixJobRunner``   — cloud + matrix (runs all combos on one VPS)
    * ``CloudFleetRunner``       — cloud + fleet (one VPS per chunk)

    Imports are lazy to avoid pulling heavy cloud dependencies when they
    are not needed.
    """
    has_cloud = getattr(job, "cloud", None)
    has_matrix = job.strategy and job.strategy.matrix
    has_fleet = job.strategy and job.strategy.fleet

    if has_cloud and has_fleet:
        from ofx.runner.execution.cloud_fleet import CloudFleetRunner

        return CloudFleetRunner(job, ctx, parent=parent)

    if has_cloud and has_matrix:
        from ofx.runner.execution.cloud_matrix import CloudMatrixJobRunner

        return CloudMatrixJobRunner(job, ctx, parent=parent)

    if has_cloud:
        from ofx.runner.execution.cloud_job import CloudJobRunner

        return CloudJobRunner(job, ctx, parent=parent)

    if has_matrix:
        from ofx.runner.execution.job import MatrixJobRunner

        return MatrixJobRunner(job, ctx, parent=parent)

    from ofx.runner.execution.job import JobRunner

    return JobRunner(job, ctx, parent=parent)
