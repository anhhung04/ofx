"""Matrix combination generation utilities.

Centralises the Cartesian-product + include/exclude logic that was
previously duplicated across ``MatrixJobRunner``,
``CloudMatrixJobRunner``, and ``WorkflowExecutionManager``.
"""

from __future__ import annotations

import itertools
from typing import Any

MAX_MATRIX_COMBINATIONS = 10_000


def generate_matrix_combinations(
    matrix: dict[str, list[Any]] | None,
    *,
    include: list[dict[str, Any]] | None = None,
    exclude: list[dict[str, Any]] | None = None,
    enforce_limit: bool = True,
) -> list[dict[str, Any]]:
    """Generate all matrix combinations with include/exclude rules.

    Args:
        matrix: Mapping of key → list-of-values for Cartesian expansion.
        include: Extra combinations to append (if not already present).
        exclude: Filter combinations matching any of these dicts.
        enforce_limit: When ``True`` (default), raises ``ValueError`` if
            the estimated combination count exceeds
            ``MAX_MATRIX_COMBINATIONS``.

    Returns:
        List of ``{key: value, ...}`` dicts, one per combination.
    """
    if not matrix:
        return []

    matrix_keys = list(matrix.keys())
    matrix_values = [matrix[key] for key in matrix_keys]

    if enforce_limit:
        estimated = 1
        for vals in matrix_values:
            estimated *= len(vals) if isinstance(vals, list) else 1
            if estimated > MAX_MATRIX_COMBINATIONS:
                raise ValueError(
                    f"Matrix would produce ~{estimated} combinations "
                    f"(limit: {MAX_MATRIX_COMBINATIONS}). "
                    f"Reduce matrix values or add exclude rules."
                )

    base_combinations = [
        dict(zip(matrix_keys, combination, strict=True))
        for combination in itertools.product(*matrix_values)
    ]

    if exclude:
        base_combinations = [
            combo
            for combo in base_combinations
            if not _matches_any_filter(combo, exclude)
        ]

    if include:
        for include_combo in include:
            if include_combo not in base_combinations:
                base_combinations.append(include_combo)

    return base_combinations


def estimate_matrix_count(
    matrix: dict[str, list[Any]] | None,
    *,
    include: list[dict[str, Any]] | None = None,
    exclude: list[dict[str, Any]] | None = None,
) -> int:
    """Return the number of combinations without enforcing the limit.

    Cheaper than ``generate_matrix_combinations`` when you only need
    the count (used by ``WorkflowExecutionManager`` for progress display).
    """
    combos = generate_matrix_combinations(
        matrix, include=include, exclude=exclude, enforce_limit=False
    )
    return max(len(combos), 1)


def _matches_any_filter(combo: dict[str, Any], filters: list[dict[str, Any]]) -> bool:
    """Check if *combo* matches any filter dict (all keys must match)."""
    for filter_dict in filters:
        if all(combo.get(key) == value for key, value in filter_dict.items()):
            return True
    return False
