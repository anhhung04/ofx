"""Command and script execution models."""

from pathlib import Path

from pydantic import Field

from ofx.models.base import OFXBaseModel
from ofx.settings import DEFAULT_SHELL

class Command(OFXBaseModel):
    """Model for shell command execution."""

    cmd: str = Field(
        default="<should_be_replaced>", description="Shell command to execute"
    )
    shell: str = Field(default=DEFAULT_SHELL, description="Shell to use for execution")
    working_directory: Path = Field(
        default_factory=Path.cwd, description="Working directory for command execution"
    )
    timeout_minutes: int = Field(
        default=1440, description="Timeout in minutes for command execution"
    )
    interactive: bool = Field(
        default=False, description="Enable interactive mode (stdin/stdout passthrough)"
    )

class Script(Command):
    """Model for Python script execution."""

    script: str = Field(..., description="Python script code to execute")
