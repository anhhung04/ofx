"""Command and script runners for executing shell commands and Python scripts"""

import asyncio
import base64
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

from ofx.models.command import Command, Script
from ofx.runner.core import BaseRunner, RunContext
from ofx.settings import DEFAULT_SHELL, settings

logger = logging.getLogger(settings.app_branding)


class CommandRunner(BaseRunner[Command]):
    """Optimized command runner with caching."""

    _shell_cache: dict[str, str] = {}

    def __init__(
        self,
        cmd: str,
        ctx: RunContext,
        shell: str = DEFAULT_SHELL,
        working_dir: Path | None = None,
        timeout_minutes: int = 1440,
        parent: "BaseRunner | None" = None,
        interactive: bool = False,
    ):
        command_model = Command(
            cmd=cmd,
            shell=shell,
            working_directory=working_dir or Path.cwd(),
            timeout_minutes=timeout_minutes,
            interactive=interactive,
        )
        super().__init__(command_model, ctx, parent)
        self._outputs_file: Path | None = None

    async def _do_run(self) -> None:
        """Execute a shell command and capture output"""
        stderr = ""
        stdout = ""
        exit_code = None
        proc = None

        if not self.model.shell or not Path(self.model.shell).exists():
            raise RuntimeError(f"Shell not found: {self.model.shell}") from None

        if not self.model.interactive:
            self._outputs_file = Path(
                tempfile.mkstemp(prefix="ofx_outputs_", suffix=".txt")[1]
            )
            self.ctx.envs["OFX_OUTPUTS"] = str(self._outputs_file)

        try:
            if self.model.interactive:
                logger.info(
                    self._produce_log(
                        "Running in interactive mode (stdin/stdout connected to terminal)"
                    )
                )
                proc = await asyncio.create_subprocess_shell(
                    self.model.cmd,
                    executable=self.model.shell,
                    cwd=self.model.working_directory,
                    env=self.ctx.envs,
                    stdin=sys.stdin,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                )

                try:
                    exit_code = await asyncio.wait_for(
                        proc.wait(), self.model.timeout_minutes * 60
                    )
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
                    raise RuntimeError(
                        f"Command timed out after {self.model.timeout_minutes} minutes"
                    ) from None

                stdout = "[Interactive mode - output shown in real-time]"
                stderr = ""
            else:
                proc = await asyncio.create_subprocess_shell(
                    self.model.cmd,
                    executable=self.model.shell,
                    cwd=self.model.working_directory,
                    env=self.ctx.envs,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        proc.communicate(), self.model.timeout_minutes * 60
                    )
                    exit_code = proc.returncode
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
                    raise RuntimeError(
                        f"Command timed out after {self.model.timeout_minutes} minutes"
                    ) from None

                max_size = settings.max_output_size

                try:
                    stderr = stderr_bytes.decode("utf-8").strip()
                    stdout = stdout_bytes.decode("utf-8").strip()

                    if len(stdout_bytes) > max_size:
                        stdout = (
                            stdout_bytes[:max_size].decode("utf-8", errors="ignore")
                            + "\n... [OUTPUT TRUNCATED]"
                        )
                        self._result.outputs["output_truncated"] = True

                    if len(stderr_bytes) > max_size:
                        stderr = (
                            stderr_bytes[:max_size].decode("utf-8", errors="ignore")
                            + "\n... [STDERR TRUNCATED]"
                        )
                        self._result.outputs["stderr_truncated"] = True

                except UnicodeDecodeError:
                    if len(stdout_bytes) > max_size:
                        stdout = (
                            base64.b64encode(stdout_bytes[:max_size]).decode("utf-8")
                            + "... [BINARY OUTPUT TRUNCATED]"
                        )
                        self._result.outputs["binary_output"] = True
                        self._result.outputs["output_truncated"] = True
                    else:
                        stdout = base64.b64encode(stdout_bytes).decode("utf-8")
                        self._result.outputs["binary_output"] = True

                    if len(stderr_bytes) > max_size:
                        stderr = (
                            base64.b64encode(stderr_bytes[:max_size]).decode("utf-8")
                            + "... [BINARY STDERR TRUNCATED]"
                        )
                        self._result.outputs["stderr_truncated"] = True
                    else:
                        stderr = base64.b64encode(stderr_bytes).decode("utf-8")

            if self.model.interactive:
                if exit_code not in (0, 130, 127):
                    stderr = stderr or f"Command failed with exit code {exit_code}"
                    raise RuntimeError(f"Command failed: {stderr}") from None
            else:
                if exit_code != 0:
                    stderr = stderr or f"Command failed with exit code {exit_code}"
                    raise RuntimeError(f"Command failed: {stderr}") from None

        except TimeoutError:
            raise RuntimeError(
                f"Command timed out after {self.model.timeout_minutes} minutes"
            ) from None
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Command error: {str(e)}") from e
        finally:
            # Properly close subprocess to avoid event loop warnings
            if proc is not None:
                try:
                    if proc.returncode is None:
                        proc.kill()
                        await asyncio.wait_for(proc.wait(), timeout=1.0)
                except Exception:
                    pass  # Ignore cleanup errors

            # self._result.outputs.update(
            #     {
            #         "stdout": stdout,
            #         "stderr": stderr,
            #         "exit_code": exit_code,
            #     }
            # )

            if self._outputs_file and self._outputs_file.exists():
                try:
                    outputs_content = self._outputs_file.read_text().strip()
                    if outputs_content:
                        for line in outputs_content.splitlines():
                            line = line.strip()
                            if line and "=" in line:
                                key, value = line.split("=", 1)
                                key = key.strip()
                                value = value.strip()
                                # if key:
                                #     self._result.outputs[key] = value
                                #     logger.debug(
                                #         self._produce_log(
                                #             f"Captured output: {key}={value}"
                                #         )
                                #     )
                except Exception as e:
                    logger.warning(
                        self._produce_log(f"Failed to parse OFX_OUTPUTS: {e}")
                    )
                finally:
                    try:
                        self._outputs_file.unlink()
                    except Exception:
                        pass

    async def _pre_run(self) -> None:
        self.model.shell = self._resolve_shell()

    async def _post_run(self) -> None:
        if self._error:
            logger.error(self._produce_log(f"Command failed: {self._error}"))
        logger.debug(
            self._produce_log(
                f"cmd result: \n---\n{await self.get_result()}\n---\n with context: \n---\n{self.ctx}\n---"
            )
        )

    def _produce_log(self, message: Any) -> str:
        msg = str(message)
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    def _resolve_shell(self) -> str:
        """Resolve shell path from hierarchy or use default /bin/bash"""
        if self.model.shell:
            return self.model.shell

        parent = getattr(self, "parent", None)
        if parent and getattr(parent, "parent", None):
            grandparent = parent.parent
            grandparent_model = getattr(grandparent, "model", None)
            if grandparent_model:
                defaults = getattr(grandparent_model, "defaults", None)
                if defaults and hasattr(defaults, "run"):
                    parent_shell = getattr(defaults.run, "shell", None)
                    if parent_shell:
                        return parent_shell

        return DEFAULT_SHELL


class ScriptRunner(BaseRunner[Script]):
    def __init__(
        self,
        script: str,
        ctx: RunContext,
        shell: str = DEFAULT_SHELL,
        working_dir: Path | None = None,
        timeout_minutes: int = 1440,
        parent: "BaseRunner | None" = None,
        interactive: bool = False,
    ):
        script_model = Script(
            script=script,
            shell=shell,
            working_directory=working_dir or Path.cwd(),
            timeout_minutes=timeout_minutes,
            interactive=interactive,
            interpreter=sys.executable or "python3",
        )
        super().__init__(script_model, ctx, parent)
        self._command_runner: CommandRunner = CommandRunner(
            cmd=self.model.cmd,
            shell=self.model.shell,
            working_dir=self.model.working_directory,
            timeout_minutes=self.model.timeout_minutes,
            parent=self.parent,
            ctx=self.ctx,
            interactive=self.model.interactive,
        )

    async def _do_run(self) -> None:
        """Execute a Python script"""
        result = await self._command_runner.run()
        self._result = result
        if result.status.value != "completed":
            raise RuntimeError(result.error or "Script execution failed")

    async def _pre_run(self) -> None:
        """Pre-run hook"""
        pass

    async def _post_run(self) -> None:
        if self._error:
            logger.error(self._produce_log(f"Script failed: {self._error}"))
        if self.model.script_file and self.model.script_file.exists():
            self.model.script_file.unlink(missing_ok=True)

    def _produce_log(self, message: Any) -> str:
        msg = str(message)
        if self.parent:
            return self.parent._produce_log(msg)
        return msg
