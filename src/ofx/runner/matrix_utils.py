"""Matrix combination generation utilities."""

from __future__ import annotations

import itertools
from collections.abc import Callable
from typing import Any

MAX_MATRIX_COMBINATIONS = 10_000
ValueProcessor = Callable[[Any], Any]


def generate_matrix_combinations(
    matrix: dict[str, Any] | None,
    *,
    include: list[dict[str, Any]] | None = None,
    exclude: list[dict[str, Any]] | None = None,
    enforce_limit: bool = True,
    value_processor: ValueProcessor | None = None,
) -> list[dict[str, Any]]:
    """Generate all matrix combinations with include/exclude rules."""
    if not matrix:
        return []

    matrix_keys = list(matrix.keys())
    matrix_values = [_matrix_values(matrix[key]) for key in matrix_keys]

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
        _process_values(
            dict(zip(matrix_keys, combination, strict=True)), value_processor
        )
        for combination in itertools.product(*matrix_values)
    ]

    if exclude:
        exclude = [_process_values(item, value_processor) for item in exclude]
        base_combinations = [
            combo
            for combo in base_combinations
            if not _matches_any_filter(combo, exclude)
        ]

    if include:
        for include_combo in include:
            include_combo = _process_values(include_combo, value_processor)
            if include_combo not in base_combinations:
                base_combinations.append(include_combo)

    return base_combinations


def estimate_matrix_count(
    matrix: dict[str, Any] | None,
    *,
    include: list[dict[str, Any]] | None = None,
    exclude: list[dict[str, Any]] | None = None,
) -> int:
    """Return the number of combinations without enforcing the limit."""
    combos = generate_matrix_combinations(
        matrix, include=include, exclude=exclude, enforce_limit=False
    )
    return max(len(combos), 1)


def _matrix_values(value: Any) -> list[Any]:
    """Return a list of values for one matrix dimension."""
    return value if isinstance(value, list) else [value]


def _process_values(
    values: dict[str, Any], value_processor: ValueProcessor | None
) -> dict[str, Any]:
    """Apply optional matrix value processing to a combination/filter."""
    if value_processor is None:
        return dict(values)
    return {key: value_processor(value) for key, value in values.items()}


def _matches_any_filter(combo: dict[str, Any], filters: list[dict[str, Any]]) -> bool:
    """Check if *combo* matches any filter dict."""
    for filter_dict in filters:
        if all(combo.get(key) == value for key, value in filter_dict.items()):
            return True
    return False


__all__ = [
    "MAX_MATRIX_COMBINATIONS",
    "estimate_matrix_count",
    "generate_matrix_combinations",
]
