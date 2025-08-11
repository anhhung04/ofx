from pydantic import BaseModel, Field
from typing import Union, List, Dict
from ofx.models.step import Step
from ofx.models import DefaultConfig


class Job(BaseModel):
    name: str = Field(..., description="Name of the job")
    needs: Union[str, List[str]] = Field(
        [],
        description="Job dependencies (other jobs that must complete before this one)",
    )
    run_if: str = Field(
        "", description="Condition to run the job (e.g., 'success()', 'failure()')"
    )
    env: Dict[str, str] = Field(
        default={},
        description="A map of variables that are available to all steps in the job",
    )
    outputs: Dict[str, str] = Field(
        {}, description="Outputs of the job (key-value pairs)"
    )
    defaults: DefaultConfig = Field(
        default_factory=lambda: DefaultConfig(),
        description="Default configuration for the job",
    )
    steps: List[Step] = Field(..., description="List of steps in the job")
