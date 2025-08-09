import re

from pydantic import BaseModel, Field, model_validator
from typing import Union, List, Dict, Any, Literal
from ofx.models.job import Job
from ofx.models import DefaultConfig


class WorkflowInput(BaseModel):
    required: bool = Field(default=False, description="Whether the input is required")
    default: Any = Field(None, description="Default value for the input parameter")
    type: Union[Literal["string"], Literal["number"], Literal["boolean"]] = Field(
        "string", description="Type of the input parameter (e.g., 'string', 'number')"
    )


class WorkflowSecret(BaseModel):
    required: bool = Field(default=False, description="Whether the secret is required")
    type: Union[Literal["string"], Literal["number"], Literal["boolean"]] = Field(
        "string", description="Type of the secret (e.g., 'string', 'number')"
    )


class WorkflowCall(BaseModel):
    inputs: Dict[str, WorkflowInput] = Field(
        default={}, description="Inputs for the reusable workflow"
    )
    outputs: Dict[str, str] = Field({}, description="Outputs of the reusable workflow")
    secrets: Dict[str, WorkflowSecret] = Field(
        {},
        description="Secrets to pass to the reusable workflow (key-value pairs)",
    )


class WorkflowDispatch(BaseModel):
    inputs: Dict[str, WorkflowInput] = Field(
        default={}, description="Inputs for the workflow dispatch event"
    )


class Workflow(BaseModel):
    name: str = Field(..., description="Name of the workflow")
    description: str = Field(
        "No provided description", description="Description of the workflow"
    )
    schedule: str = Field("", description="Cron schedule for the workflow")
    env: Dict[str, str] = Field(
        default={}, description="Environment variables for the workflow"
    )
    workflow_dispatch: WorkflowDispatch = Field(
        default_factory=lambda: WorkflowDispatch(),
        description="Workflow dispatch configuration for manual triggers",
    )
    workflow_call: WorkflowCall = Field(
        default_factory=lambda: WorkflowCall(),
        description="Workflow call configuration for reusable workflows",
    )
    tags: List[str] = Field([], description="Tags associated with the workflow")
    defaults: DefaultConfig = Field(
        default_factory=lambda: DefaultConfig(),
        description="Default configuration for the workflow",
    )
    jobs: Dict[str, Job] = Field(..., description="List of jobs in the workflow")

    @model_validator(mode="after")
    def check_jobid_pattern(self):
        """
        Ensure that the job ID pattern is valid.
        """
        for job_id in self.jobs.keys():
            if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
                raise ValueError(f"Job {job_id} does not have a valid pattern defined.")
            if isinstance(self.jobs[job_id].needs, str):
                self.jobs[job_id].needs = [self.jobs[job_id].needs]
            for dep in self.jobs[job_id].needs:
                if dep and dep not in self.jobs:
                    raise ValueError(
                        f"Job {job_id} has a dependency on {dep}, which does not exist."
                    )

        return self
