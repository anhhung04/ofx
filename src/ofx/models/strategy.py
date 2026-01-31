"""Matrix strategy for job variations."""

from typing import Any

from pydantic import Field

from ofx.models.base import OFXBaseModel


class MatrixStrategy(OFXBaseModel):
    """Matrix strategy for running job variations."""

    matrix: dict[str, list[Any]] = Field(
        ...,
        description="Matrix variables with lists of values to create job combinations",
    )
    max_parallel: int = Field(
        default=10000000,
        description="Maximum number of matrix jobs to run in parallel per stage (default: unlimited)",
    )
    fail_fast: bool = Field(
        default=True,
        description="Whether to fail the entire matrix if one job fails (default: true)",
    )
    include: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Additional matrix combinations to include",
    )
    exclude: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Matrix combinations to exclude from execution",
    )
