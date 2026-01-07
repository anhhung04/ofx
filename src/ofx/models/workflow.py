import re
from typing import Any, Literal
from pathlib import Path
from pydantic import BaseModel, Field, model_validator

from ofx.models import DefaultConfig
from ofx.models.job import Job


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


class ToolConfig(BaseModel):
    """Configuration for tool installation and verification"""
    install: str = Field(..., description="Command to install the tool")
    check: None | str = Field(
        None, description="Command to check if tool is already installed (exit 0 = installed)"
    )
    post_install: None | str = Field(
        None, description="Command to run after successful installation"
    )


class WorkflowCall(BaseModel):
    inputs: dict[str, WorkflowInput] = Field(
        default_factory=dict, description="Inputs for the reusable workflow"
    )
    outputs: dict[str, str] = Field(default_factory=dict, description="Outputs of the reusable workflow")
    secrets: dict[str, WorkflowSecret] = Field(
        default_factory=dict,
        description="Secrets to pass to the reusable workflow (key-value pairs)",
    )


class WorkflowDispatch(BaseModel):
    inputs: dict[str, WorkflowInput] = Field(
        default_factory=dict, description="Inputs for the workflow dispatch event"
    )


class Workflow(BaseModel):
    name: str = Field(..., description="Name of the workflow")
    description: str = Field(
        "No provided description", description="Description of the workflow"
    )
    env: dict[str, str] = Field(
        default_factory=dict, description="Environment variables for the workflow"
    )
    workflow_dispatch: None | WorkflowDispatch = Field(
        None,
        description="Workflow dispatch configuration for manual triggers",
    )
    workflow_call: None | WorkflowCall = Field(
        None,
        description="Workflow call configuration for reusable workflows",
    )
    workflow_path:  Path = Field(
        Path.cwd(), description="Path to the workflow file (set automatically)"
    )
    tools: None | dict[str, str | ToolConfig] = Field(
        None, description="Tools configuration - can be simple command string or ToolConfig object"
    )
    tags: list[str] = Field(default_factory=list, description="Tags associated with the workflow")
    defaults: DefaultConfig = Field(
        default_factory=DefaultConfig,
        description="Default configuration for the workflow",
    )
    jobs: dict[str, Job] = Field(..., min_length=1, description="List of jobs in the workflow")

    def __str__(self):
        return f"Workflow(name='{self.name}', jobs='{list(self.jobs.keys())}')"

    @model_validator(mode="after")
    def validate_jobs(self):
        """
        Ensure that the job definitions are valid:
        - Job IDs have a valid pattern.
        - Job dependencies exist.
        - There are no circular dependencies.
        - jid, step.name and step_index are populated.
        """
        job_keys = self.jobs.keys()
        for job_id, job in self.jobs.items():
            if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
                raise ValueError(f"Job ID '{job_id}' does not have a valid pattern. Use letters, numbers, hyphens, and underscores.")

            needs = job.needs
            if isinstance(needs, str):
                needs = [needs]
            for dep in needs:
                if dep and dep not in job_keys:
                    raise ValueError(
                        f"Job '{job_id}' has a dependency on '{dep}', which does not exist."
                    )

            self.jobs[job_id].jid = job_id
            for idx, step in enumerate(job.steps):
                step.step_index = idx
                if not step.name:
                    step.name = f"{job_id}-step-{idx}"

        graph = {job_id: set(job.needs) for job_id, job in self.jobs.items()}
        path = set()
        visited = set()

        def visit(vertex):
            path.add(vertex)
            for neighbour in graph.get(vertex, set()):
                if neighbour in path:
                    raise ValueError(f"Circular dependency detected in jobs: {path}")
                if neighbour not in visited:
                    visit(neighbour)
            path.remove(vertex)
            visited.add(vertex)

        for job_id in job_keys:
            if job_id not in visited:
                visit(job_id)

        return self