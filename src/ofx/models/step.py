import uuid
from pydantic import BaseModel, Field
from typing import Union, Dict, Any, Literal


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
    timeout_minutes: int = Field(
        60 * 24, description="Timeout in minutes for the step execution"
    )
    run: Union[str, None] = Field(None, description="Command(s) to run in the step")
    working_directory: str = Field(
        ".", description="Working directory for the step execution"
    )
    shell: Union[str, None] = Field(
        None, description="Shell to use for running commands in the step"
    )
    log_stdout: bool = Field(
        False, description="Whether to capture standard output of the step"
    )
    uses: Union[str, None] = Field(
        None, description="Select a workflow to run as part of a step in the job"
    )
    run_with: Dict[str, Any] = Field(
        {},
        description="Define inputs for the step if it uses a reusable workflow",
    )
    script: Union[None, str] = Field(
        None, description="Script to run in the step (if applicable)"
    )
    secrets: Union[Union[Dict[str, str], Literal["inherit"]]] = Field(
        {},
        description="Secrets to pass to the step (key-value pairs) if it uses a reusable workflow",
    )
