"""Command and script runners for executing shell commands and Python scripts"""

import base64
import logging
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from zlib import compress

from ofx.runner.base import BaseRunner
from ofx.runner.models import RunContext
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class CommandRunner(BaseRunner):
    def __init__(
        self,
        cmd: str,
        ctx: RunContext,
        shell: str | None = None,
        working_dir: Path | None = None,
        timeout_minutes: int = 1440,
        parent: "BaseRunner | None" = None,
    ):
        super().__init__("command", ctx, parent)
        self._cmd = cmd
        self._shell = shell
        self._cwd = working_dir or Path.cwd()
        self._timeout_minutes = timeout_minutes

    async def _do_run(self):
        """Execute a shell command and capture output"""
        stderr = ""
        stdout = ""
        exit_code = None
        
        if not self._shell or not Path(self._shell).exists():
            raise RuntimeError(f"Shell not found: {self._shell}")
        
        args = [self._shell, "-c", self._cmd]
        
        try:
            output = subprocess.run(
                args,
                cwd=self._cwd,
                env=self.ctx_vars.envs,
                timeout=self._timeout_minutes * 60,
                capture_output=True,
            )
            exit_code = output.returncode
            
            try:
                stderr = output.stderr.decode("utf-8").strip()
                stdout = output.stdout.decode("utf-8").strip()
            except UnicodeDecodeError:
                stderr = base64.b64encode(output.stderr).decode("utf-8")
                stdout = base64.b64encode(output.stdout).decode("utf-8")
                self._result.outputs["binary_output"] = True
            
            if output.returncode != 0:
                stderr = stderr or f"Command failed with exit code {output.returncode}"
                raise RuntimeError(f"Command failed: {stderr}")
                
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Command timed out after {self._timeout_minutes} minutes")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Command error: {str(e)}")
        finally:
            # Always update outputs, even on error
            self._result.outputs.update({
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
            })

    async def _pre_run(self):
        self._shell = self._resolve_shell()

    async def _post_run(self):
        if self._error:
            logger.error(self._produce_log(f"Command failed: {self._error}"))
        logger.debug(
            self._produce_log(
                f"cmd result: \n---\n{self.get_result()}\n---\n with context: \n---\n{self.ctx_vars}\n---"
            )
        )

    def _produce_log(self, message: Any) -> str:
        msg = str(message)
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    def _resolve_shell(self) -> str:
        """Resolve shell path from hierarchy or use default /bin/bash"""
        if self._shell:
            return self._shell
        
        parent = getattr(self, 'parent', None)
        if parent and getattr(parent, 'parent', None):
            grandparent = parent.parent
            grandparent_model = getattr(grandparent, 'model', None)
            if grandparent_model:
                defaults = getattr(grandparent_model, 'defaults', None)
                if defaults and hasattr(defaults, 'run'):
                    parent_shell = getattr(defaults.run, 'shell', None)
                    if parent_shell:
                        return parent_shell
        
        return "/bin/bash"


class ScriptRunner(CommandRunner):
    def __init__(
        self,
        script: str,
        ctx: RunContext,
        shell: str | None = None,
        working_dir: Path | None = None,
        timeout_minutes: int = 1440,
        parent: BaseRunner | None = None,
    ):
        self._tmp_file = None
        self._run_in_file = False
        enc_script = base64.b64encode(compress(script.encode(), 9)).decode()
        python_executable = sys.executable or "python3"
        if len(enc_script) > 2000:
            self._run_in_file = True
            self._tmp_file = tempfile.mktemp(suffix=".py")
            with open(self._tmp_file, "w") as f:
                f.write("import base64,zlib\n")
                f.write(
                    f"exec(zlib.decompress(base64.b64decode('{enc_script}')).decode('utf-8'))\n"
                )
            args = [python_executable, self._tmp_file]
        else:
            args = [
                python_executable,
                "-Wignore",
                "-c",
                f"import base64,zlib;exec(zlib.decompress(base64.b64decode('{enc_script}')).decode('utf-8'))",
            ]
        super().__init__(
            cmd=shlex.join(args),
            shell=shell,
            working_dir=working_dir,
            timeout_minutes=timeout_minutes,
            parent=parent,
            ctx=ctx,
        )

    async def _post_run(self):
        if self._error:
            logger.error(self._produce_log(f"Script failed: {self._error}"))
        if self._run_in_file and self._tmp_file and Path(self._tmp_file).exists():
            Path(self._tmp_file).unlink()
