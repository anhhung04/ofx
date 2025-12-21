import re

from pydantic import BaseModel, Field, model_validator
from typing import Union, List, Dict, Any, Literal
from ofx.models.job import Job
from ofx.models import DefaultConfig


class WorkflowInput(BaseModel):
    required: bool = Field(default=False, description="Whether the input is required")
    default: Any = Field(None, description="Default value for the input parameter")
    type: Literal["string", "number", "array", "object", "boolean"] = Field(
        "string", description="Type of the input parameter (e.g., 'string', 'number')"
    )


class WorkflowSecret(BaseModel):
    required: bool = Field(default=False, description="Whether the secret is required")
    type: Literal["string", "number", "array", "object", "boolean"] = Field(
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
    workflow_dispatch: Union[None, WorkflowDispatch] = Field(
        None,
        description="Workflow dispatch configuration for manual triggers",
    )
    workflow_call: Union[None, WorkflowCall] = Field(
        None,
        description="Workflow call configuration for reusable workflows",
    )
    tools: Union[None, Dict[str, Any]] = Field(
        None, description="Needed tools for the workflow"
    )
    tags: List[str] = Field([], description="Tags associated with the workflow")
    defaults: DefaultConfig = Field(
        default_factory=lambda: DefaultConfig(),
        description="Default configuration for the workflow",
    )
    hooks: Dict[str, str] = Field(
        default={},
        description="Lifecycle hooks with Python code (e.g., pre_run, post_run, on_error)",
    )
    jobs: Dict[str, Job] = Field(..., description="List of jobs in the workflow")

    def __str__(self):
        return f"Workflow(name='{self.name}', jobs='{list(self.jobs.keys())}')"

    @model_validator(mode="after")
    def check_jobid_pattern(self):
        """
        Ensure that the job ID pattern is valid.
        """
        for job_id in self.jobs.keys():
            if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
                raise ValueError(f"Job {job_id} does not have a valid pattern defined.")
            defined_needs = self.jobs[job_id].needs
            needs =  defined_needs if isinstance(defined_needs, list) else [defined_needs]
            for dep in needs:
                if dep and dep not in self.jobs:
                    raise ValueError(
                        f"Job {job_id} has a dependency on {dep}, which does not exist."
                    )
            self.jobs[job_id].jid = job_id
            for idx, step in enumerate(self.jobs[job_id].steps):
                step.step_index = idx
        return self
