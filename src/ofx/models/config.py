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

class DurableRunConfig(OFXBaseModel):
    """Durable execution configuration for workflows."""

    enabled: bool = Field(
        default=True,
        description="Enable durable checkpoints for workflow execution",
    )
    resume: bool = Field(
        default=True,
        description="Resume from last completed step when checkpoints exist",
    )
    backend: str = Field(
        default="file",
        description="Durable backend: file or redis",
    )
    redis_prefix: str = Field(
        default="ofx:durable:",
        description="Redis key prefix for durable checkpoints",
    )
    auto_commit: bool = Field(
        default=False,
        description="Auto-commit output directory to git after workflow completion",
        alias="auto-commit",
    )
    auto_push: bool = Field(
        default=False,
        description="Auto-push committed checkpoint data to git remote (implies auto-commit)",
        alias="auto-push",
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
    durable: DurableRunConfig = Field(
        default_factory=DurableRunConfig,
        description="Durable execution configuration",
    )
    profile: str = Field(
        default="",
        description=(
            "Name of a profile from ~/.ofx/profiles.yml to apply. "
            "Provides rate limits, time windows, and tool option overrides."
        ),
    )
    store_creds: bool = Field(
        default=False,
        description=(
            "Automatically store discovered UserAccount credentials from task "
            "outputs into the credential store. Can be overridden per-step "
            "with 'store-creds: true/false'."
        ),
        alias="store-creds",
    )
