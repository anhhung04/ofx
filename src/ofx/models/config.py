"""Configuration models for workflows and jobs."""

from pathlib import Path

from pydantic import Field

from ofx.models.base import OFXBaseModel
from ofx.settings import DEFAULT_SHELL, DEFAULT_WORKFLOWS_DIR


class RunConfig(OFXBaseModel):
    """Shell and working directory configuration."""

    shell: str = Field(
        default=DEFAULT_SHELL,
        description="Shell to use for running commands in the workflow",
    )
    working_directory: Path = Field(
        default_factory=Path.cwd,
        description="Working directory for the workflow execution",
    )


class DefaultConfig(OFXBaseModel):
    """Default configuration for workflows."""

    run: RunConfig = Field(
        default_factory=RunConfig,
        description="Default run configuration for the workflow",
    )
    workflows_base_dir: Path = Field(
        default=DEFAULT_WORKFLOWS_DIR,
        description="Base directory for workflows (if applicable)",
    )
    flow_registry_url: str = Field(
        default="https://github.com",
        description="Base URL for the flow registry",
    )
