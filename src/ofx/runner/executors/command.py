import sys
import base64
import subprocess
import tempfile
import shlex
import logging

from pathlib import Path
from typing import Any, TYPE_CHECKING, Optional
from zlib import compress

from ofx.runner.core.models import RunContext, RunnerStatus
from ofx.runner.core.template import TemplateEngine
from ofx.settings import settings

if TYPE_CHECKING:
    from ofx.runner.base import BaseRunner

logger = logging.getLogger(settings.app_branding)

DEFAULT_SHELL = "/bin/bash"


class CommandExecutor:
    def __init__(
        self,
        cmd: str,
        ctx: RunContext,
        runner: "BaseRunner",
        shell: Optional[str] = None,
        working_dir: Optional[Path] = None,
        timeout_minutes: int = 1440,
    ):
        self._cmd = cmd
        self._ctx = ctx
        self._runner = runner
        self._shell = shell
        self._cwd = working_dir or Path.cwd()
        self._timeout_minutes = timeout_minutes
        self._template_engine = TemplateEngine(runner)

    async def execute(self) -> dict[str, Any]:
        """Execute command with timeout and hook support."""
        stderr = ""
        stdout = ""
        binary_output = False
        
        shell = self._resolve_shell()
        if not shell or not Path(shell).exists():
            raise RuntimeError(f"Shell not found: {shell}")
        
        args = [shell, "-c", self._cmd]
        try:
            output = subprocess.run(
                args,
                cwd=self._cwd,
                env=self._ctx.envs,
                timeout=self._timeout_minutes * 60,
                capture_output=True,
            )
            try:
                stderr = output.stderr.decode("utf-8").strip()
                stdout = output.stdout.decode("utf-8").strip()
            except UnicodeDecodeError:
                stderr = base64.b64encode(output.stderr).decode("utf-8")
                stdout = base64.b64encode(output.stdout).decode("utf-8")
                binary_output = True

            if output.returncode != 0:
                stderr = stderr or f"Command failed with exit code {output.returncode}"
                raise RuntimeError(f"Command failed: {stderr}")

        except subprocess.TimeoutExpired:
            stderr = f"Command timed out after {self._timeout_minutes} minutes"
            # Execute ON_TIMEOUT hook
            await self._execute_timeout_hook()
            raise RuntimeError(stderr)

        except Exception as e:
            if not stderr:
                stderr = str(e)
            raise RuntimeError(f"Command error: {stderr}")
        
        result = {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": output.returncode if "output" in locals() else None,
        }
        if binary_output:
            result["binary_output"] = True
        
        return result

    def _resolve_shell(self) -> str:
        """Resolve shell - expects shell to be passed in directly."""
        return self._shell or DEFAULT_SHELL
    
    async def _execute_timeout_hook(self):
        """Execute ON_TIMEOUT hook when command times out."""
        try:
            from ofx.runner.core.hooks import HookPoint, HookContext
            hook_ctx = HookContext(
                model=self._runner.model if hasattr(self._runner, 'model') else None,
                command=self._cmd,
                runner=self._runner,
            )
            if hasattr(self._runner, '_hook_handler'):
                await self._runner._hook_handler.execute_hooks(HookPoint.ON_TIMEOUT, hook_ctx)
        except Exception as e:
            logger.error(f"Error executing timeout hook: {e}")


class ScriptExecutor:
    """Executor for running scripts with timeout and hook support."""
    def __init__(
        self,
        script: str,
        ctx: RunContext,
        runner: "BaseRunner",
        shell: Optional[str] = None,
        working_dir: Optional[Path] = None,
        timeout_minutes: int = 1440,
    ):
        self._script = script
        self._ctx = ctx
        self._runner = runner
        self._shell = shell
        self._cwd = working_dir or Path.cwd()
        self._timeout_minutes = timeout_minutes
        self._tmp_file = None
        self._run_in_file = False

    async def execute(self) -> dict[str, Any]:
        enc_script = base64.b64encode(compress(self._script.encode(), 9)).decode()
        python_executable = sys.executable or "python3"
        
        if len(enc_script) > 2000:
            self._run_in_file = True
            self._tmp_file = tempfile.mktemp(suffix=".py")
            with open(self._tmp_file, "w") as f:
                f.write(f"import base64,zlib\n")
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
        
        cmd = shlex.join(args)
        executor = CommandExecutor(
            cmd=cmd,
            ctx=self._ctx,
            runner=self._runner,
            shell=self._shell,
            working_dir=self._cwd,
            timeout_minutes=self._timeout_minutes,
        )
        
        try:
            result = await executor.execute()
            return result
        finally:
            if self._run_in_file and self._tmp_file and Path(self._tmp_file).exists():
                Path(self._tmp_file).unlink()
