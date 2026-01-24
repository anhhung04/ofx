from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from ofx.models.config import DefaultConfig
from ofx.models.step import Step
from ofx.settings import DEFAULT_SHELL


class MatrixStrategy(BaseModel):
    """Matrix strategy for running job variations"""

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


class Job(BaseModel):
    name: str = Field(default="", description="Name of the job")
    needs: str | list[str] = Field(
        default_factory=list,
        description="Job dependencies (other jobs that must complete before this one)",
    )
    run_if: str | bool = Field(
        default=True,
        description="Condition to run the job (e.g., 'success()', 'failure()')",
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
    )
    fail_fast: bool = Field(
        default=True,
        description="Whether to fail the entire matrix if one job fails",
    )

    @model_validator(mode="after")
    def normalize_needs(self):
        """Normalize needs to always be a list."""
        if isinstance(self.needs, str):
            self.needs = [self.needs] if self.needs else []
        elif self.needs is None:
            self.needs = []
        return self

    def __str__(self):
        return f"Job(name='{self.name}',id={self.jid})"
