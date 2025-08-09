import re

from pydantic import BaseModel, Field, model_validator
from typing import Optional, Union, List, Dict, Any, Literal
from ofx.models.job import Job
from ofx.models import DefaultConfig


class WorkflowInput(BaseModel):
    required: bool = Field(default=False, description="Whether the input is required")
    default: Optional[Any] = Field(
        None, description="Default value for the input parameter"
    )
    type: Optional[Union[Literal["string"], Literal["number"], Literal["boolean"]]] = (
        Field(
            None, description="Type of the input parameter (e.g., 'string', 'number')"
        )
    )


class WorkflowSecret(BaseModel):
    required: bool = Field(default=False, description="Whether the secret is required")
    type: Optional[Union[Literal["string"], Literal["number"], Literal["boolean"]]] = (
        Field(None, description="Type of the secret (e.g., 'string', 'number')")
    )


class WorkflowCall(BaseModel):
    inputs: Dict[str, WorkflowInput] = Field(
        default={}, description="Inputs for the reusable workflow"
    )
    outputs: Optional[Dict[str, str]] = Field(
        None, description="Outputs of the reusable workflow"
    )
    secrets: Optional[Union[Dict[str, WorkflowSecret]]] = Field(
        None,
        description="Secrets to pass to the reusable workflow (key-value pairs)",
    )


class WorkflowDispatch(BaseModel):
    inputs: Dict[str, WorkflowInput] = Field(
        default={}, description="Inputs for the workflow dispatch event"
    )


class Workflow(BaseModel):
    name: str = Field(..., description="Name of the workflow")
    description: Optional[str] = Field(None, description="Description of the workflow")
    schedule: Optional[str] = Field(None, description="Cron schedule for the workflow")
    env: Dict[str, str] = Field(
        default={}, description="Environment variables for the workflow"
    )
    workflow_dispatch: Optional[WorkflowDispatch] = Field(
        None, description="Workflow dispatch configuration for manual triggers"
    )
    workflow_call: Optional[WorkflowCall] = Field(
        None, description="Workflow call configuration for reusable workflows"
    )
    tags: Optional[List[str]] = Field(
        None, description="Tags associated with the workflow"
    )
    defaults: Optional[DefaultConfig] = Field(
        None, description="Default configuration for the workflow"
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
        return self
