"""Command and tool installation models"""

from pathlib import Path

from pydantic import BaseModel, Field

from ofx.settings import DEFAULT_SHELL


class Command(BaseModel):
    """Model for shell command execution"""

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

    def __str__(self):
        cmd = self.cmd.split(" ")[0]
        return f"Command(cmd='{cmd}',cwd='{self.working_directory}')"


class Script(Command):
    """Model for Python script execution"""

    script: str = Field(..., description="Python script code to execute")
    interpreter: str = Field(
        default="python3", description="Code interpreter to use for execution"
    )

    def __str__(self):
        return f"Script(inline,cwd='{self.working_directory}')"
