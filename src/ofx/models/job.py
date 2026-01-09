from pathlib import Path
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    from cython import cython_function_or_method  # type: ignore
except Exception:  # pragma: no cover - cython optional
    cython_function_or_method = type(lambda: None)

from ofx.models import DefaultConfig
from ofx.models.step import Step


class MatrixStrategy(BaseModel):
    """Matrix strategy for running job variations"""
    matrix: dict[str, list[Any]] = Field(
        ...,
        description="Matrix variables with lists of values to create job combinations",
    )
    max_parallel: int | None = Field(
        None,
        description="Maximum number of matrix jobs to run in parallel (default: unlimited)",
    )
    fail_fast: bool = Field(
        True,
        description="Whether to cancel remaining matrix jobs when one fails",
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
    model_config: ClassVar = ConfigDict(
        ignored_types=(type(lambda: None), cython_function_or_method)
    )
    name: str | None = Field(None, description="Name of the job")
    needs: str | list[str] = Field(
        default_factory=list,
        description="Job dependencies (other jobs that must complete before this one)",
    )
    run_if: str | bool = Field(
        True, description="Condition to run the job (e.g., 'success()', 'failure()')"
    )
    strategy: MatrixStrategy | None = Field(
        None,
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
    hooks: dict[str, str] = Field(
        default_factory=dict,
        description="Lifecycle hooks with Python code (e.g., pre_run, post_run, on_iter_step)",
    )
    steps: list[Step] = Field(..., min_length=1, description="List of steps in the job")
    jid: str = Field(
        default="",
        description="Job identifier in the workflow",
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
        return f"Job(name='{self.name}', id={self.jid})"

    def get_shell(self, workflow_defaults: Optional["DefaultConfig"] = None) -> str | None:
        """Get shell from job defaults or inherit from workflow."""
        if self.defaults and self.defaults.run.shell:
            return self.defaults.run.shell
        if workflow_defaults and workflow_defaults.run.shell:
            return workflow_defaults.run.shell
        return None

    def get_working_directory(self, workflow_defaults: Optional["DefaultConfig"] = None) -> Path:
        """Get working directory from job defaults or inherit from workflow."""
        if self.defaults and self.defaults.run.working_directory:
            return Path(self.defaults.run.working_directory)
        if workflow_defaults and workflow_defaults.run.working_directory:
            return Path(workflow_defaults.run.working_directory)
        return Path.cwd()
