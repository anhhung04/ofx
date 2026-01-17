from pathlib import Path

from pydantic import BaseModel, Field

from ofx.settings import DEFAULT_SHELL, DEFAULT_WORKFLOWS_DIR


class RunConfig(BaseModel):
    shell: str = Field(
        default=DEFAULT_SHELL,
        description="Shell to use for running commands in the workflow",
    )
    working_directory: str | Path = Field(
        default_factory=Path.cwd,
        description="Working directory for the workflow execution",
    )


class DefaultConfig(BaseModel):
    run: RunConfig = Field(
        default_factory=RunConfig,
        description="Default run configuration for the workflow",
    )
    workflows_base_dir: Path = Field(
        default=DEFAULT_WORKFLOWS_DIR,
        description="Base directory for workflows (if applicable)",
    )
