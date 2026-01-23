"""Matrix utilities for OFX framework."""

import itertools
import json
import logging
from typing import Any

from ofx.models.job import Job, MatrixStrategy
from ofx.settings import settings


def expand_jobs(jobs: dict[str, Job]) -> dict[str, Job]:
    """Expand jobs with matrix strategies into individual job instances, auto-injecting needs for max_parallel."""
    logger = logging.getLogger(settings.app_branding)
    expanded_jobs: dict[str, Job] = {}

    for job_id, job in jobs.items():
        if job.strategy and job.strategy.matrix:
            matrix_combinations = _generate_matrix_combinations(job.strategy)
            max_parallel = job.strategy.max_parallel if job.strategy else None
            fail_fast = job.strategy.fail_fast if job.strategy else True
            expanded_ids = []
            for idx, matrix_values in enumerate(matrix_combinations):
                expanded_job_id = f"{job_id}_{idx}"
                expanded_ids.append(expanded_job_id)
                expanded_job = job.model_copy(
                    deep=True,
                    update={
                        "jid": expanded_job_id,
                        "matrix_values": matrix_values,
                        "original_job_id": job_id,
                        "matrix_index": idx,
                        "max_parallel": max_parallel,
                        "fail_fast": fail_fast,
                    },
                )
                expanded_jobs[expanded_job_id] = expanded_job
                logger.debug(
                    f"Expanded matrix job '{job_id}' -> '{job_id}_{idx}' with matrix: {matrix_values}"
                )
            # Inject needs dependencies for max_parallel
            if max_parallel and max_parallel > 0:
                for idx, expanded_job_id in enumerate(expanded_ids):
                    if idx >= max_parallel:
                        # Each job beyond the first n depends on previous n jobs
                        needs = expanded_ids[max(0, idx - max_parallel) : idx]
                        expanded_jobs[expanded_job_id].needs = needs
        else:
            expanded_job = job.model_copy(deep=True)
            expanded_job.jid = job_id
            expanded_job.matrix_values = {}
            expanded_job.original_job_id = job_id
            expanded_job.matrix_index = None
            expanded_job.max_parallel = None
            expanded_job.fail_fast = True
            expanded_jobs[job_id] = expanded_job

    return expanded_jobs


def _generate_matrix_combinations(strategy: MatrixStrategy) -> list[dict[str, Any]]:
    """Generate all matrix combinations with include/exclude rules

    Args:
        strategy: Matrix strategy configuration

    Returns:
        List of matrix value combinations
    """
    matrix_keys = list(strategy.matrix.keys())
    matrix_values = [strategy.matrix[key] for key in matrix_keys]

    # Generate base combinations (cartesian product)
    base_combinations = [
        dict(zip(matrix_keys, combination, strict=True))
        for combination in itertools.product(*matrix_values)
    ]

    # Apply exclude rules
    if strategy.exclude:
        base_combinations = [
            combo
            for combo in base_combinations
            if not _matches_matrix_filter(combo, strategy.exclude)
        ]

    # Apply include rules
    if strategy.include:
        for include_combo in strategy.include:
            if include_combo not in base_combinations:
                base_combinations.append(include_combo)

    return base_combinations


def _matches_matrix_filter(
    combo: dict[str, Any], filters: list[dict[str, Any]]
) -> bool:
    """Check if a combination matches any filter

    Args:
        combo: Matrix combination to check
        filters: List of filter dictionaries

    Returns:
        True if combination matches any filter
    """
    for filter_dict in filters:
        if all(combo.get(key) == value for key, value in filter_dict.items()):
            return True
    return False


def process_matrix_value(value: Any) -> Any:
    """Process a matrix value, attempting JSON parsing if it's a string

    Args:
        value: Raw matrix value

    Returns:
        Processed value (parsed JSON if applicable)
    """
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value


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
