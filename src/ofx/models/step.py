from pydantic import BaseModel, Field
from typing import Optional, Union, Dict, Any, Literal


class Step(BaseModel):
    name: str = Field(..., description="Name of the step")
    id: Optional[str] = Field(None, description="Unique identifier for the step")
    run_if: Optional[str] = Field(
        None, description="Condition to run the step (e.g., 'success()', 'failure()')"
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
    run: Optional[str] = Field(None, description="Command(s) to run in the step")
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
