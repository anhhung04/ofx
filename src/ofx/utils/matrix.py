"""Matrix utilities for OFX framework."""

from ofx.models.job import Job, MatrixStrategy

def expand_jobs(jobs: dict[str, Job]) -> dict[str, Job]:
    """Process jobs, keeping matrix jobs as single units for MatrixJobRunner to handle."""
    processed_jobs: dict[str, Job] = {}

    for job_id, job in jobs.items():
        if job.strategy and job.strategy.matrix:
            processed_job = job.model_copy(deep=True)
            processed_job.jid = job_id
            processed_job.matrix_values = {}
            processed_job.original_job_id = job_id
            processed_job.matrix_index = None
            processed_job.max_parallel = job.strategy.max_parallel
            processed_job.fail_fast = job.strategy.fail_fast
            processed_jobs[job_id] = processed_job
        else:
            processed_job = job.model_copy(deep=True)
            processed_job.jid = job_id
            processed_job.matrix_values = {}
            processed_job.original_job_id = job_id
            processed_job.matrix_index = None
            processed_job.max_parallel = None
            processed_job.fail_fast = True
            processed_jobs[job_id] = processed_job

    return processed_jobs

def get_expanded_job_ids(
    expanded_jobs: dict[str, Job], original_job_id: str
) -> list[str]:
    """Get all expanded job IDs for an original job

    Args:
        expanded_jobs: Dictionary of expanded jobs
        original_job_id: Original job ID before expansion

    Returns:
        List of expanded job IDs
    """
    expanded_ids = []
    for expanded_job_id, job in expanded_jobs.items():
        if job.original_job_id == original_job_id:
            expanded_ids.append(expanded_job_id)
    return expanded_ids if expanded_ids else [original_job_id]
