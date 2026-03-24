"""Matrix utilities for OFX framework."""

import itertools
import json
from typing import Any

from ofx.models.job import Job, MatrixStrategy


def expand_jobs(jobs: dict[str, Job]) -> dict[str, Job]:
    """Process jobs, keeping matrix jobs as single units for MatrixJobRunner to handle."""
    processed_jobs: dict[str, Job] = {}

    for job_id, job in jobs.items():
        if job.strategy and job.strategy.matrix:
            # Keep matrix jobs as single units, MatrixJobRunner will expand internally
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


def _generate_matrix_combinations(strategy: MatrixStrategy) -> list[dict[str, Any]]:
    """Generate all matrix combinations with include/exclude rules

    Args:
        strategy: Matrix strategy configuration

    Returns:
        List of matrix value combinations

    Raises:
        ValueError: If the estimated combination count exceeds 10,000
    """
    MAX_MATRIX_COMBINATIONS = 10_000

    matrix_keys = list(strategy.matrix.keys())
    matrix_values = [strategy.matrix[key] for key in matrix_keys]

    # Pre-check: estimate combination count without materializing
    estimated = 1
    for vals in matrix_values:
        estimated *= len(vals) if isinstance(vals, list) else 1
        if estimated > MAX_MATRIX_COMBINATIONS:
            raise ValueError(
                f"Matrix would produce ~{estimated} combinations "
                f"(limit: {MAX_MATRIX_COMBINATIONS}). "
                f"Reduce matrix values or add exclude rules."
            )

    # Generate base combinations (cartesian product)
    base_combinations = [
        dict(zip(matrix_keys, combination, strict=True))
        for combination in itertools.product(*matrix_values)
    ]

    # Process matrix values (e.g., parse JSON strings)
    processed_combinations = []
    for combo in base_combinations:
        processed_combo = {}
        for key, value in combo.items():
            processed_combo[key] = process_matrix_value(value)
        processed_combinations.append(processed_combo)
    base_combinations = processed_combinations

    # Apply exclude rules
    if strategy.exclude:
        processed_exclude = []
        for exclude_filter in strategy.exclude:
            processed_filter = {}
            for key, value in exclude_filter.items():
                processed_filter[key] = process_matrix_value(value)
            processed_exclude.append(processed_filter)
        base_combinations = [
            combo
            for combo in base_combinations
            if not _matches_matrix_filter(combo, processed_exclude)
        ]

    # Apply include rules
    if strategy.include:
        for include_combo in strategy.include:
            processed_include = {}
            for key, value in include_combo.items():
                processed_include[key] = process_matrix_value(value)
            if processed_include not in base_combinations:
                base_combinations.append(processed_include)

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
