from pydantic import BaseModel, Field
from typing import Optional


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
    workflows_base_dir: Optional[str] = Field(
        None, description="Base directory for workflows (if applicable)"
    )
