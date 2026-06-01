"""Workflow model and related types."""

import re
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from ofx.models.base import OFXBaseModel
from ofx.models.config import DefaultConfig
from ofx.models.inputs import WorkflowInput, WorkflowSecret
from ofx.models.job import Job
from ofx.models.tools import ToolConfig


class WorkflowCall(OFXBaseModel):
    """Configuration for reusable workflow calls."""

    inputs: dict[str, WorkflowInput] = Field(
        default_factory=dict, description="Inputs for the reusable workflow"
    )
    outputs: dict[str, str] = Field(
        default_factory=dict, description="Outputs of the reusable workflow"
    )
    secrets: dict[str, WorkflowSecret] = Field(
        default_factory=dict,
        description="Secrets to pass to the reusable workflow (key-value pairs)",
    )


class WorkflowDispatch(OFXBaseModel):
    """Configuration for manual workflow triggers."""

    inputs: dict[str, WorkflowInput] = Field(
        default_factory=dict, description="Inputs for the workflow dispatch event"
    )


class Workflow(BaseModel):
    """Main workflow definition."""

    name: str = Field(..., description="Name of the workflow")
    description: str = Field(
        "No provided description", description="Description of the workflow"
    )
    tags: list[str] = Field(
        default_factory=list, description="Tags associated with the workflow"
    )
    dispatch: None | WorkflowDispatch = Field(
        default=None,
        description="Workflow dispatch configuration for manual triggers",
    )
    call: None | WorkflowCall = Field(
        default=None,
        description="Workflow call configuration for reusable workflows",
    )
    env: dict[str, str] = Field(
        default_factory=dict, description="Environment variables for the workflow"
    )
    tools: dict[str, str | ToolConfig] = Field(
        default_factory=dict,
        description="Tools configuration - can be simple command string or ToolConfig object",
    )
    defaults: DefaultConfig = Field(
        default_factory=DefaultConfig,
        description="Default configuration for the workflow",
    )
    outputs: dict[str, str] = Field(
        default_factory=dict,
        description="Workflow-level outputs mapped from job outputs",
    )
    jobs: dict[str, Job] = Field(..., description="List of jobs in the workflow")
    workflow_path: Path = Field(
        default_factory=Path.cwd,
        description="Path to the workflow file (set automatically)",
    )

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
        if len(job_keys) == 0:
            raise ValueError("Workflow must have at least one job defined.")
        for job_id, job in self.jobs.items():
            if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
                raise ValueError(
                    f"Job ID '{job_id}' does not have a valid pattern. Use letters, numbers, hyphens, and underscores."
                )

            needs = job.needs
            if isinstance(needs, str):
                needs = [needs]
            for dep in needs:
                if dep and dep not in job_keys:
                    raise ValueError(
                        f"Job '{job_id}' has a dependency on '{dep}', which does not exist."
                    )

            self.jobs[job_id].jid = job_id
            step_names: set[str] = set()
            for idx, step in enumerate(job.steps):
                step.step_index = idx
                if not step.name or step.name == "<should_be_replaced>":
                    step.name = f"{job_id}-step-{idx}"
                if step.name in step_names:
                    raise ValueError(
                        f"Job '{job_id}' has duplicate step name '{step.name}'. "
                        "Step names must be unique within a job."
                    )
                step_names.add(step.name)

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
