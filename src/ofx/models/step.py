import uuid
from pydantic import BaseModel, Field
from typing import Union, Dict, Any, Literal, Optional, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from ofx.models import DefaultConfig


class Step(BaseModel):
    name: str = Field(..., description="Name of the step")
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the step",
    )
    run_if: Union[str, bool] = Field(
        True, description="Condition to run the step (e.g., 'success()', 'failure()')"
    )
    env: Dict[str, str] = Field(
        default={},
        description="Environment variables for the step",
    )
    continue_on_error: bool = Field(
        default=False, description="Continue execution even if the step fails"
    )
    timeout: int = Field(
        60 * 24, description="Timeout in minutes for the step execution"
    )
    max_attempts: int = Field(
        1, description="Maximum number of retry attempts for the step (default: 1, no retries)"
    )
    run: Optional[str] = Field(None, description="Command(s) to run in the step")
    working_directory: str = Field(
        ".", description="Working directory for the step execution"
    )
    shell: Optional[str] = Field(
        None, description="Shell to use for running commands in the step"
    )
    log_stdout: bool | str = Field(
        False, description="Whether to capture standard output of the step"
    )
    uses: Optional[str] = Field(
        None, description="Select a workflow to run as part of a step in the job"
    )
    run_with: Dict[str, Any] = Field(
        {},
        description="Define inputs for the step if it uses a reusable workflow",
    )
    script: Optional[str] = Field(
        None, description="Script to run in the step (if applicable)"
    )
    secrets: Union[Dict[str, str], Literal["inherit"]] = Field(
        {},
        description="Secrets to pass to the step (key-value pairs) if it uses a reusable workflow",
    )
    hooks: Dict[str, str] = Field(
        default={},
        description="Lifecycle hooks with Python code (e.g., before_step, after_step, on_retry, on_skip, on_timeout)",
    )
    step_index: int = Field(
        -1, description="Index of the step in the job (set during execution)"
    )

    def get_shell(self, job_defaults: Optional["DefaultConfig"] = None, workflow_defaults: Optional["DefaultConfig"] = None) -> str | None:
        """Get shell from step, job defaults, or workflow defaults."""
        if self.shell:
            return self.shell
        if job_defaults and job_defaults.run.shell:
            return job_defaults.run.shell
        if workflow_defaults and workflow_defaults.run.shell:
            return workflow_defaults.run.shell
        return None

    def get_working_directory(self, job_defaults: Optional["DefaultConfig"] = None, workflow_defaults: Optional["DefaultConfig"] = None) -> Path:
        """Get working directory from step, job, or workflow defaults."""
        step_path = Path(self.working_directory)
        if step_path.is_absolute():
            return step_path
        
        # Get job working directory
        if job_defaults and job_defaults.run.working_directory:
            job_path = Path(job_defaults.run.working_directory)
            if job_path.is_absolute():
                return job_path / step_path
        
        # Get workflow working directory
        if workflow_defaults and workflow_defaults.run.working_directory:
            workflow_path = Path(workflow_defaults.run.working_directory)
            job_rel_path = Path(job_defaults.run.working_directory) if job_defaults else Path(".")
            return workflow_path / job_rel_path / step_path
        
        return Path.cwd() / step_path

    def __str__(self):
        return f"Step(name='{self.name}', id={self.id})"
