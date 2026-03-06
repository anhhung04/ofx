"""Command execution helper for subprocess handling."""

from __future__ import annotations

import asyncio
import base64
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ofx.models.command import Command
from ofx.runner.commands.shell_functions import get_shell_functions
from ofx.settings import settings


@dataclass
class CommandExecutionResult:
    exit_code: int | None
    stdout: str
    stderr: str
    outputs: dict[str, Any]


class CommandExecutor:
    """Handles subprocess execution for CommandRunner."""

    def __init__(self, command: Command, envs: dict[str, Any]):
        self._command = command
        self._envs = envs
        self._outputs_file: Path | None = None

    @property
    def outputs_file(self) -> Path | None:
        return self._outputs_file

    async def execute(self) -> CommandExecutionResult:
        if self._command.interactive:
            return await self._run_interactive()
        return await self._run_non_interactive()

    def prepare_outputs_file(self) -> None:
        if not self._command.interactive:
            self._outputs_file = Path(
                tempfile.mkstemp(prefix=".tmp_out_", suffix=".txt")[1]
            )
            self._envs["RUNNER_OUTPUTS"] = str(self._outputs_file)

    async def _run_interactive(self) -> CommandExecutionResult:
        # Prepend shell helper functions to the command
        shell_funcs = get_shell_functions(self._command.shell)
        full_cmd = f"{shell_funcs}\n{self._command.cmd}"

        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            executable=self._command.shell,
            cwd=self._command.working_directory,
            env=self._envs,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        try:
            exit_code = await asyncio.wait_for(
                proc.wait(), self._command.timeout_minutes * 60
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(
                f"Command timed out after {self._command.timeout_minutes} minutes"
            ) from None
        finally:
            self._close_process(proc)

        return CommandExecutionResult(
            exit_code=exit_code,
            stdout="[Interactive mode - output shown in real-time]",
            stderr="",
            outputs={},
        )

    async def _run_non_interactive(self) -> CommandExecutionResult:
        # Prepend shell helper functions to the command
        shell_funcs = get_shell_functions(self._command.shell)
        full_cmd = f"{shell_funcs}\n{self._command.cmd}"

        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            executable=self._command.shell,
            cwd=self._command.working_directory,
            env=self._envs,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), self._command.timeout_minutes * 60
            )
            exit_code = proc.returncode
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(
                f"Command timed out after {self._command.timeout_minutes} minutes"
            ) from None
        finally:
            self._close_process(proc)

        stdout, stderr, outputs = self._decode_output(stdout_bytes, stderr_bytes)
        return CommandExecutionResult(
            exit_code=exit_code, stdout=stdout, stderr=stderr, outputs=outputs
        )

    def _decode_output(
        self, stdout_bytes: bytes, stderr_bytes: bytes
    ) -> tuple[str, str, dict[str, Any]]:
        max_size = settings.max_output_size
        outputs: dict[str, Any] = {}
        try:
            stderr = stderr_bytes.decode("utf-8").strip()
            stdout = stdout_bytes.decode("utf-8").strip()

            if len(stdout_bytes) > max_size:
                stdout = (
                    stdout_bytes[:max_size].decode("utf-8", errors="ignore")
                    + "\n... [OUTPUT TRUNCATED]"
                )
                outputs["output_truncated"] = True

            if len(stderr_bytes) > max_size:
                stderr = (
                    stderr_bytes[:max_size].decode("utf-8", errors="ignore")
                    + "\n... [STDERR TRUNCATED]"
                )
                outputs["stderr_truncated"] = True

        except UnicodeDecodeError:
            if len(stdout_bytes) > max_size:
                stdout = (
                    base64.b64encode(stdout_bytes[:max_size]).decode("utf-8")
                    + "... [BINARY OUTPUT TRUNCATED]"
                )
                outputs["binary_output"] = True
                outputs["output_truncated"] = True
            else:
                stdout = base64.b64encode(stdout_bytes).decode("utf-8")
                outputs["binary_output"] = True

            if len(stderr_bytes) > max_size:
                stderr = (
                    base64.b64encode(stderr_bytes[:max_size]).decode("utf-8")
                    + "... [BINARY STDERR TRUNCATED]"
                )
                outputs["stderr_truncated"] = True
            else:
                stderr = base64.b64encode(stderr_bytes).decode("utf-8")

        return stdout, stderr, outputs

    def raise_for_status(self, exit_code: int | None, stderr: str) -> None:
        if self._command.interactive:
            if exit_code not in (0, 130, 127):
                stderr = stderr or f"Command failed with exit code {exit_code}"
                raise RuntimeError(f"Command failed: {stderr}") from None
            return
        if exit_code != 0:
            stderr = stderr or f"Command failed with exit code {exit_code}"
            raise RuntimeError(f"Command failed: {stderr}") from None

    @staticmethod
    def _close_process(proc: asyncio.subprocess.Process) -> None:
        transport = getattr(proc, "_transport", None)
        if transport is None:
            return
        try:
            transport.close()
        except Exception:
            pass

    async def capture_outputs_file(self, runner, key: str, log_fn) -> None:
        if not self._outputs_file or not self._outputs_file.exists():
            return
        try:
            outputs_content = self._outputs_file.read_text().strip()
            if outputs_content:
                for line in outputs_content.splitlines():
                    line = line.strip()
                    if line and "=" in line:
                        key_name, value = line.split("=", 1)
                        key_name = key_name.strip()
                        value = value.strip()
                        if key_name:
                            await runner.reg_update(key, {key_name: value})
                            log_fn(f"Captured output: {key_name}={value}")
        except Exception as e:
            log_fn(f"Failed to parse RUNNER_OUTPUTS: {e}")
        finally:
            try:
                self._outputs_file.unlink()
            except Exception:
                pass
