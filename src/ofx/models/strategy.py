"""Matrix strategy for job variations."""

from typing import Any, Literal

from pydantic import Field, field_validator

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

    matrix: dict[str, list[Any] | str] = Field(
        default_factory=dict,
        description="Matrix variables — lists of values or a template string that resolves to a JSON list at runtime",
    )
    max_parallel: int = Field(
        default=4,
        ge=1,
        description="Maximum number of matrix jobs to run in parallel per stage",
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

    @field_validator("matrix")
    @classmethod
    def _validate_matrix_keys(cls, v: dict[str, list[Any] | str]) -> dict[str, list[Any] | str]:
        """Ensure matrix keys are valid identifiers (used as template variables)."""
        import re

        for key in v:
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
                raise ValueError(
                    f"Matrix key '{key}' is not a valid identifier. "
                    f"Use letters, digits, and underscores only (e.g. 'my_var')."
                )
        return v
