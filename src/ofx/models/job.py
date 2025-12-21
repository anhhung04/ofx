from pydantic import BaseModel, Field, model_validator
from typing import Union, List, Dict, Union, Optional
from pathlib import Path

from ofx.models.step import Step
from ofx.models import DefaultConfig


class Job(BaseModel):
    name: Optional[str] = Field(None, description="Name of the job")
    needs: Union[str, List[str]] = Field(
        [],
        description="Job dependencies (other jobs that must complete before this one)",
    )
    run_if: Union[str, bool] = Field(
        True, description="Condition to run the job (e.g., 'success()', 'failure()')"
    )
    env: Dict[str, str] = Field(
        default={},
        description="A map of variables that are available to all steps in the job",
    )
    outputs: Dict[str, str] = Field(
        {}, description="Outputs of the job (key-value pairs)"
    )
    defaults: DefaultConfig = Field(
        default_factory=DefaultConfig,
        description="Default configuration for the job",
    )
    hooks: Dict[str, str] = Field(
        default={},
        description="Lifecycle hooks with Python code (e.g., pre_run, post_run, on_iter_step)",
    )
    steps: List[Step] = Field(..., description="List of steps in the job")
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
