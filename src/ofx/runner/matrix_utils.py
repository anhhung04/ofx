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
    matrix_values = [
        value if isinstance(value, list) else [value]
        for value in matrix.values()
    ]

    if enforce_limit:
        _enforce_matrix_limit(matrix_values)

    base_combinations = [
        _process_values(
            dict(zip(matrix_keys, combination, strict=True)),
            value_processor,
        )
        for combination in itertools.product(*matrix_values)
    ]

    if exclude:
        processed_excludes = [
            _process_values(filter_dict, value_processor)
            for filter_dict in exclude
        ]
        base_combinations = [
            combo
            for combo in base_combinations
            if not any(
                all(combo.get(key) == value for key, value in filter_dict.items())
                for filter_dict in processed_excludes
            )
        ]

    if include:
        for include_combo in (
            _process_values(filter_dict, value_processor)
            for filter_dict in include
        ):
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

def _enforce_matrix_limit(matrix_values: list[list[Any]]) -> None:
    """Raise when a matrix would exceed the supported combination limit."""
    estimated = _estimate_combinations(matrix_values)
    if estimated <= MAX_MATRIX_COMBINATIONS:
        return
    raise ValueError(
        f"Matrix would produce ~{estimated} combinations "
        f"(limit: {MAX_MATRIX_COMBINATIONS}). "
        f"Reduce matrix values or add exclude rules."
    )

def _estimate_combinations(matrix_values: list[list[Any]]) -> int:
    """Return the cartesian-product size for normalized matrix values."""
    estimated = 1
    for values in matrix_values:
        estimated *= len(values)
        if estimated > MAX_MATRIX_COMBINATIONS:
            return estimated
    return estimated

def _process_values(
    values: dict[str, Any], value_processor: ValueProcessor | None
) -> dict[str, Any]:
    """Apply optional matrix value processing to a combination/filter."""
    if value_processor is None:
        return dict(values)
    return {key: value_processor(value) for key, value in values.items()}

__all__ = [
    "MAX_MATRIX_COMBINATIONS",
    "estimate_matrix_count",
    "generate_matrix_combinations",
]
