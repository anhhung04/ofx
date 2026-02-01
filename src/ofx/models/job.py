"""Job model for workflow execution."""

from typing import Any

from pydantic import Field, model_validator

from ofx.models.base import OFXBaseModel
from ofx.models.config import DefaultConfig
from ofx.models.step import Step
from ofx.models.strategy import MatrixStrategy


class Job(OFXBaseModel):
    """Job definition within a workflow."""

    name: str = Field(default="", description="Name of the job")
    needs: str | list[str] = Field(
        default_factory=list,
        description="Job dependencies (other jobs that must complete before this one)",
    )
    run_if: str | bool = Field(
        default=True,
        description="Condition to run the job (e.g., 'success()', 'failure()')",
        alias="if",
    )
    strategy: MatrixStrategy | None = Field(
        default=None,
        description="Matrix strategy for running multiple variations of the job",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="A map of variables that are available to all steps in the job",
    )
    outputs: dict[str, str] = Field(
        default_factory=dict, description="Outputs of the job (key-value pairs)"
    )
    defaults: DefaultConfig = Field(
        default_factory=DefaultConfig,
        description="Default configuration for the job",
    )
    steps: list[Step] = Field(..., min_length=1, description="List of steps in the job")
    jid: str = Field(
        default="",
        description="Job identifier in the workflow",
    )
    matrix_values: dict[str, Any] = Field(
        default_factory=dict,
        description="Matrix values for this job instance (populated during expansion)",
    )
    original_job_id: str = Field(
        default="",
        description="Original job ID before matrix expansion",
    )
    matrix_index: int | None = Field(
        default=None,
        description="Index of this job in the matrix expansion",
    )
    max_parallel: int | None = Field(
        default=None,
        description="Maximum number of matrix jobs to run in parallel",
        alias="max-parallel",
    )
    fail_fast: bool = Field(
        default=True,
        description="Whether to fail the entire matrix if one job fails",
        alias="fail-fast",
    )

    @model_validator(mode="after")
    def normalize_needs(self):
        """Normalize needs to always be a list."""
        if isinstance(self.needs, str):
            object.__setattr__(self, "needs", [self.needs] if self.needs else [])
        elif self.needs is None:
            object.__setattr__(self, "needs", [])
        return self

    @model_validator(mode="after")
    def set_matrix_fields(self):
        """Set max_parallel and fail_fast from strategy if present."""
        if self.strategy:
            if self.strategy.max_parallel is not None:
                object.__setattr__(self, "max_parallel", self.strategy.max_parallel)
            if self.strategy.fail_fast is not None:
                object.__setattr__(self, "fail_fast", self.strategy.fail_fast)
        return self

    def __str__(self):
        return f"Job(name='{self.name}',id={self.jid})"
