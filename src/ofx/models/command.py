"""Command and tool installation models"""

from pathlib import Path

from pydantic import BaseModel, Field


class Command(BaseModel):
    """Model for shell command execution"""

    cmd: str = Field(..., description="Shell command to execute")
    shell: str | None = Field(None, description="Shell to use for execution")
    working_directory: Path = Field(
        default=Path.cwd(), description="Working directory for command execution"
    )
    timeout_minutes: int = Field(
        default=1440, description="Timeout in minutes for command execution"
    )
    interactive: bool = Field(
        default=False, description="Enable interactive mode (stdin/stdout passthrough)"
    )

    def __str__(self):
        return f"Command(cmd='{self.cmd[:50]}...' if len(self.cmd) > 50 else self.cmd)"


class Script(BaseModel):
    """Model for Python script execution"""

    script: str = Field(..., description="Python script code to execute")
    shell: str | None = Field(None, description="Shell to use for execution")
    working_directory: Path = Field(
        default=Path.cwd(), description="Working directory for script execution"
    )
    timeout_minutes: int = Field(
        default=1440, description="Timeout in minutes for script execution"
    )
    interactive: bool = Field(
        default=False, description="Enable interactive mode (stdin/stdout passthrough)"
    )

    def __str__(self):
        script_preview = self.script[:30] if len(self.script) > 30 else self.script
        return f"Script(script='{script_preview}...')"
