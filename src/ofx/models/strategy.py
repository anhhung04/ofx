"""Matrix strategy for job variations."""

from typing import Any, Literal

from pydantic import Field

from ofx.models.base import OFXBaseModel


class FleetStrategy(OFXBaseModel):
    """Fleet distribution strategy for running across multiple VPS instances."""

    count: int = Field(..., ge=1, description="Number of fleet instances")
    input: str | list[str] = Field(
        default="",
        description="Input to distribute: file path, CIDR, IP list, or mixed",
    )
    distribution: Literal["chunk", "round-robin", "subnet", "line"] = Field(
        default="chunk",
        description="Distribution mode for splitting input across fleet",
    )
    expand_cidrs: bool = Field(
        default=True,
        description="Expand CIDRs to individual IPs before splitting",
    )
    min_prefix: int = Field(
        default=32,
        description="Minimum prefix length for subnet splitting",
    )
    exclude: list[str] = Field(
        default_factory=list,
        description="IPs or CIDRs to exclude from distribution",
    )


class MatrixStrategy(OFXBaseModel):
    """Matrix strategy for running job variations."""

    matrix: dict[str, list[Any]] = Field(
        default_factory=dict,
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
    fleet: FleetStrategy | None = Field(
        default=None,
        description="Fleet distribution strategy for cloud-based parallel execution",
    )
