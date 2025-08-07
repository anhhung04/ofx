from pydantic import BaseModel, Field
from typing import Optional, Union, List, Dict, Any, Literal, Type


class WorkflowInput(BaseModel):
    description: Optional[str] = Field(
        None, description="Description of the input parameter"
    )
    required: bool = Field(default=False, description="Whether the input is required")
    default: Optional[Any] = Field(
        None, description="Default value for the input parameter"
    )
    type: Optional[Type] = Field(
        None, description="Type of the input parameter (e.g., 'string', 'number')"
    )


class WorkflowOutput(BaseModel):
    description: Optional[str] = Field(
        None, description="Description of the output parameter"
    )
    value: Optional[str] = Field(
        None,
        description="A map of outputs for a called workflow. Called workflow outputs are available to all downstream jobs in the caller workflow.",
    )


class WorkflowSecret(BaseModel):
    description: Optional[str] = Field(
        None, description="Description of the secret parameter"
    )
    required: bool = Field(default=False, description="Whether the secret is required")


class WorkflowCall(BaseModel):
    inputs: Optional[Dict[str, WorkflowInput]] = Field(
        None, description="Inputs for the reusable workflow"
    )
    outputs: Optional[WorkflowOutput] = Field(
        None, description="Outputs of the reusable workflow"
    )
    secrets: Optional[Union[Dict[str, WorkflowSecret]]] = Field(
        None,
        description="Secrets to pass to the reusable workflow (key-value pairs)",
    )


class WorkflowDispatch(BaseModel):
    inputs: Optional[Dict[str, WorkflowInput]] = Field(
        None, description="Inputs for the workflow dispatch event"
    )


class ConcurencyConfig(BaseModel):
    group: str = Field(None, description="Concurrency group for the workflow")
    cancel_in_progress: bool = Field(
        default=False, description="Cancel other in-progress jobs in the group"
    )


class RunConfig(BaseModel):
    shell: str = Field(
        default="/bin/bash",
        description="Shell to use for running commands in the workflow",
    )
    working_directory: str = Field(
        default=".", description="Working directory for the workflow execution"
    )


class DefaultConfig(BaseModel):
    run: RunConfig = Field(
        default=RunConfig(),
        description="Default run configuration for the workflow",
    )


class StrategyConfig(BaseModel):
    matrix: Union[
        Dict[str, List[Any]],
        Dict[Literal["include"], Any],
        Dict[Literal["exclude"], Any],
    ] = Field(None, description="Matrix strategy for parallel execution")
    fail_fast: bool = Field(
        default=False, description="Fail fast if any matrix job fails"
    )
    max_parallel: Optional[int] = Field(
        None, description="Maximum number of parallel jobs to run"
    )


class Step(BaseModel):
    name: str = Field(..., description="Name of the step")
    id: Optional[str] = Field(None, description="Unique identifier for the step")
    run_if: Optional[str] = Field(
        None, description="Condition to run the step (e.g., 'success()', 'failure()')"
    )
    env: Optional[Dict[str, str]] = Field(
        None,
        description="Environment variables for the step",
    )
    continue_on_error: bool = Field(
        default=False, description="Continue execution even if the step fails"
    )
    timeout_minutes: int = Field(
        60 * 24, description="Timeout in minutes for the step execution"
    )
    strategy: Optional[StrategyConfig] = Field(
        None,
        description="Strategy configuration for the step (e.g., matrix strategy)",
    )
    run: Optional[str] = Field(..., description="Command(s) to run in the step")
    working_directory: Optional[str] = Field(
        None, description="Working directory for the step execution"
    )
    shell: Optional[str] = Field(
        None, description="Shell to use for running commands in the step"
    )
    uses: Optional[str] = Field(
        None, description="Select a workflow to run as part of a step in the job"
    )
    run_with: Optional[Dict[str, Any]] = Field(
        None,
        description="Define inputs for the step if it uses a reusable workflow",
    )
    script: Optional[str] = Field(
        None, description="Script to run in the step (if applicable)"
    )
    secrets: Optional[Union[Dict[str, str], Literal["inherit"]]] = Field(
        None,
        description="Secrets to pass to the step (key-value pairs) if it uses a reusable workflow",
    )


class Job(BaseModel):
    name: str = Field(..., description="Name of the job")
    needs: Optional[Union[str, List[str]]] = Field(
        None,
        description="Job dependencies (other jobs that must complete before this one)",
    )
    run_if: Optional[str] = Field(
        None, description="Condition to run the job (e.g., 'success()', 'failure()')"
    )
    env: Optional[Dict[str, str]] = Field(
        None,
        description="A map of variables that are available to all steps in the job",
    )
    concurrency: Optional[ConcurencyConfig] = Field(
        None, description="Concurrency configuration for the job"
    )
    outputs: Optional[Dict[str, str]] = Field(
        None, description="Outputs of the job (key-value pairs)"
    )
    defaults: Optional[DefaultConfig] = Field(
        None, description="Default configuration for the job"
    )
    steps: List[Step] = Field(..., description="List of steps in the job")


class Workflow(BaseModel):
    name: str = Field(..., description="Name of the workflow")
    description: Optional[str] = Field(None, description="Description of the workflow")
    schedule: Optional[str] = Field(None, description="Cron schedule for the workflow")
    concurrency: Optional[ConcurencyConfig] = Field(
        None, description="Concurrency configuration for the workflow"
    )
    env: Optional[Dict[str, str]] = Field(
        None, description="Environment variables for the workflow"
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
    jobs: Dict[str, Job] = Field(..., description="List of jobs in the workflow")
