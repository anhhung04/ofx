"""Command and tool installation models"""

import base64
import shlex
import tempfile
from pathlib import Path
from zlib import compress

from pydantic import BaseModel, Field, model_validator

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
    script_file: None | Path = Field(
        default=None, description="Path to the script file (if any)"
    )

    BASE_SCRIPT: str = "import base64,zlib;exec(zlib.decompress(base64.b64decode('{}')).decode('utf-8'))"
    MAX_SCRIPT_LENGTH: int = 1000

    @model_validator(mode="after")
    def validate_script(self):
        args = []
        DEFAULT_ARGS = ["-Wignore"]
        if len(self.script) < self.MAX_SCRIPT_LENGTH:
            enc_script = base64.b64encode(compress(self.script.encode(), 9)).decode()
            args = [
                self.interpreter,
                *DEFAULT_ARGS,
                "-c",
                self.BASE_SCRIPT.format(enc_script),
            ]
        else:
            _, tmp_path = tempfile.mkstemp(suffix=".py", text=True)
            self.script_file = Path(tmp_path)
            self.script_file.write_text(self.script)
            args = [
                self.interpreter,
                *DEFAULT_ARGS,
                self.script_file.absolute().as_posix(),
            ]
        self.cmd = shlex.join(args)
        return self

    def __str__(self):
        return f"Script(script_file='{self.script_file or 'memory'}',cwd='{self.working_directory}')"
