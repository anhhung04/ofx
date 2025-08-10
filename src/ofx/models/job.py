from pydantic import BaseModel, Field
from typing import Union, List, Dict, Any, Literal
from ofx.models.step import Step
from ofx.models import DefaultConfig


class StrategyConfig(BaseModel):
    matrix: Union[
        Dict[str, List[Any]],
        Dict[Literal["include"], Any],
        Dict[Literal["exclude"], Any],
    ] = Field(None, description="Matrix strategy for parallel execution")
    fail_fast: bool = Field(
        default=False, description="Fail fast if any matrix job fails"
    )
    max_parallel: Union[None, int] = Field(
        None, description="Maximum number of parallel jobs to run"
    )


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
    strategy: StrategyConfig = Field(
        default_factory=lambda: StrategyConfig(),
        description="Strategy configuration for the step (e.g., matrix strategy)",
    )
    outputs: Dict[str, str] = Field(
        {}, description="Outputs of the job (key-value pairs)"
    )
    defaults: DefaultConfig = Field(
        default_factory=lambda: DefaultConfig(),
        description="Default configuration for the job",
    )
    steps: List[Step] = Field(..., description="List of steps in the job")
