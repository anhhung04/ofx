import uuid
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ofx.settings import DEFAULT_SHELL

try:
    from cython import cython_function_or_method  # type: ignore
except Exception:  # pragma: no cover - cython optional
    cython_function_or_method = type(lambda: None)

if TYPE_CHECKING:
    from ofx.models import DefaultConfig


class RunType(Enum):
    """Type of step execution"""

    SCRIPT = "script"
    COMMAND = "command"
    WORKFLOW = "workflow"
    SCRIPT_FILE = "script_file"


class Step(BaseModel):
    name: str = Field(default="<should_be_replaced>", description="Name of the step")
    run_if: str | bool = Field(
        default=True,
        description="Condition to run the step (e.g., 'success()', 'failure()')",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables for the step",
    )
    continue_on_error: bool = Field(
        default=False, description="Continue execution even if the step fails"
    )
    timeout: int = Field(
        default=60 * 24, description="Timeout in minutes for the step execution"
    )
    retry: int = Field(
        default=0,
        description="Number of retry attempts on failure (default: 0, no retries)",
    )
    retry_delay: int = Field(
        default=5, description="Delay in seconds between retry attempts (default: 5)"
    )
    working_directory: Path = Field(
        default=Path.cwd(), description="Working directory for the step execution"
    )
    shell: str = Field(
        default=DEFAULT_SHELL,
        description="Shell to use for running commands in the step",
    )
    log_stdout: bool | str = Field(
        default=False, description="Whether to capture standard output of the step"
    )
    uses: str | None = Field(
        default=None,
        description="Select a workflow to run as part of a step in the job",
    )
    run: str | None = Field(default=None, description="Command(s) to run in the step")
    script: str | None = Field(
        default=None, description="Script to run in the step (if applicable)"
    )
    script_file: str | None = Field(
        default=None, description="Path to a Python script file to execute"
    )
    run_with: dict[str, Any] = Field(
        default_factory=dict,
        description="Define inputs for the step if it uses a reusable workflow",
    )
    secrets: dict[str, str] | Literal["inherit"] = Field(
        default_factory=dict,
        description="Secrets to pass to the step (key-value pairs) if it uses a reusable workflow",
    )
    hooks: dict[str, str] = Field(
        default_factory=dict,
        description="Lifecycle hooks with Python code (e.g., before_step, after_step, on_retry, on_skip, on_timeout)",
    )
    interactive: bool = Field(
        default=False,
        description="Enable interactive mode (stdin/stdout passthrough). Only works in single-job stages.",
    )
    step_index: int = Field(
        default=-1, description="Index of the step in the job (set during execution)"
    )
    model_config: ClassVar = ConfigDict(
        ignored_types=(type(lambda: None), cython_function_or_method)
    )

    @model_validator(mode="after")
    def check_run_type(self):
        """Ensure that exactly one of 'run', 'script', or 'uses' is defined."""
        defined_fields = sum(
            1
            for field in ["run", "script", "uses", "script_file"]
            if getattr(self, field) is not None
        )
        if defined_fields != 1:
            raise ValueError(
                f"Step '{self.name}' must have exactly one of 'run', 'script', 'script_file', or 'uses' defined."
            )
        return self

    def get_shell(
        self,
        job_defaults: Optional["DefaultConfig"] = None,
        workflow_defaults: Optional["DefaultConfig"] = None,
    ) -> str:
        """Get shell from step, job defaults, or workflow defaults."""
        if self.shell:
            return self.shell
        if job_defaults and job_defaults.run.shell:
            return job_defaults.run.shell
        if workflow_defaults and workflow_defaults.run.shell:
            return workflow_defaults.run.shell
        return DEFAULT_SHELL

    def get_working_directory(
        self,
        job_defaults: Optional["DefaultConfig"] = None,
        workflow_defaults: Optional["DefaultConfig"] = None,
    ) -> Path:
        """Get working directory from step, job, or workflow defaults."""
        step_path = Path(self.working_directory)
        if step_path.is_absolute():
            return step_path

        if job_defaults and job_defaults.run.working_directory:
            job_path = Path(job_defaults.run.working_directory)
            if job_path.is_absolute():
                return job_path / step_path

        if workflow_defaults and workflow_defaults.run.working_directory:
            workflow_path = Path(workflow_defaults.run.working_directory)
            job_rel_path = (
                Path(job_defaults.run.working_directory) if job_defaults else Path(".")
            )
            return workflow_path / job_rel_path / step_path

        return Path.cwd() / step_path

    def get_run_type(self) -> RunType:
        step = self
        if step.uses:
            return RunType.WORKFLOW
        elif step.script:
            return RunType.SCRIPT
        elif step.script_file:
            return RunType.SCRIPT_FILE
        elif step.run:
            return RunType.COMMAND
        raise ValueError(
            f"Step '{step.name}' must have one of 'run', 'script', 'script_file', or 'uses' defined."
        )

    def __str__(self):
        return f"Step(name='{self.name}',type='{self.get_run_type()}')"
