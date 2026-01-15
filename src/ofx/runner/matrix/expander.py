"""Matrix strategy expansion logic for job combinations"""

import itertools
import logging
from typing import Any

from ofx.models.job import MatrixStrategy
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class MatrixExpander:
    """Handles matrix strategy expansion for creating job variants"""

    @staticmethod
    def expand_jobs(jobs: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Expand jobs with matrix strategies into individual job instances

        Args:
            jobs: Dictionary of job ID to job configuration

        Returns:
            Dictionary of expanded job ID to job data including matrix values
        """
        expanded_jobs = {}

        for job_id, job in jobs.items():
            if job.strategy and job.strategy.matrix:
                matrix_combinations = MatrixExpander._generate_combinations(
                    job.strategy
                )

                for idx, matrix_values in enumerate(matrix_combinations):
                    expanded_job_id = f"{job_id}_{idx}"
                    expanded_jobs[expanded_job_id] = {
                        "job": job.model_copy(deep=True),
                        "matrix": matrix_values,
                        "original_job_id": job_id,
                        "matrix_index": idx,
                        "fail_fast": job.strategy.fail_fast,
                    }
                    logger.debug(
                        f"Expanded matrix job '{job_id}' -> '{expanded_job_id}' with matrix: {matrix_values}"
                    )
            else:
                expanded_jobs[job_id] = {
                    "job": job,
                    "matrix": {},
                    "original_job_id": job_id,
                    "matrix_index": None,
                    "fail_fast": False,
                }

        return expanded_jobs

    @staticmethod
    def _generate_combinations(strategy: MatrixStrategy) -> list[dict[str, Any]]:
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
            dict(zip(matrix_keys, combination))
            for combination in itertools.product(*matrix_values)
        ]

        # Apply exclude rules
        if strategy.exclude:
            base_combinations = [
                combo
                for combo in base_combinations
                if not MatrixExpander._matches_filter(combo, strategy.exclude)
            ]

        # Apply include rules
        if strategy.include:
            for include_combo in strategy.include:
                if include_combo not in base_combinations:
                    base_combinations.append(include_combo)

        return base_combinations

    @staticmethod
    def _matches_filter(combo: dict[str, Any], filters: list[dict[str, Any]]) -> bool:
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

    @staticmethod
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
            import json

            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value

    @staticmethod
    def get_expanded_job_ids(expanded_jobs: dict, original_job_id: str) -> list[str]:
        """Get all expanded job IDs for an original job

        Args:
            expanded_jobs: Dictionary of expanded jobs
            original_job_id: Original job ID before expansion

        Returns:
            List of expanded job IDs
        """
        expanded_ids = []
        for expanded_job_id, job_data in expanded_jobs.items():
            if job_data["original_job_id"] == original_job_id:
                expanded_ids.append(expanded_job_id)
        return expanded_ids if expanded_ids else [original_job_id]
