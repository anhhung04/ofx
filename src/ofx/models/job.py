from pydantic import BaseModel, Field
from typing import Union, List, Dict, Union, Optional

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
    steps: List[Step] = Field(..., description="List of steps in the job")
    jid: str = Field(
        default="",
        description="Job identifier in the workflow",
    )

    def __str__(self):
        return f"Job(name='{self.name}', id={self.jid})"
