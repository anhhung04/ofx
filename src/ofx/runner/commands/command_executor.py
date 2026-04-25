"""Command execution helper for subprocess handling."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import signal
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ofx.models.command import Command
from ofx.runner.commands.shell_functions import get_shell_functions
from ofx.settings import settings

logger = logging.getLogger("ofx")


@dataclass
class CommandExecutionResult:
    exit_code: int | None
    stdout: str
    stderr: str
    outputs: dict[str, Any]


def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    """Send SIGTERM to the process group, then SIGKILL if still alive.

    When subprocesses are launched with ``start_new_session=True`` the
    child becomes the session leader.  Sending a signal to the negative
    PID targets the entire process group so that grandchildren (e.g.
    nmap spawned by bash) are also cleaned up.
    """
    pid = proc.pid
    if pid is None:
        return
    try:
        pgid = os.getpgid(pid)
    except (OSError, ProcessLookupError):
        return

    # SIGTERM the group first for graceful shutdown
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass

    # Give children 2 seconds to exit, then force-kill
    import time

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)  # probe
        except (OSError, ProcessLookupError):
            return  # all dead
        time.sleep(0.1)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


class CommandExecutor:
    """Handles subprocess execution for CommandRunner."""

    def __init__(self, command: Command, envs: dict[str, Any]):
        self._command = command
        self._envs = envs
        self._outputs_file: Path | None = None

    @property
    def outputs_file(self) -> Path | None:
        """Path to the temporary outputs file, or ``None`` if not prepared."""
        return self._outputs_file

    async def execute(self) -> CommandExecutionResult:
        """Run the command and return captured output.

        Delegates to an interactive or non-interactive subprocess depending
        on the command model's ``interactive`` flag.
        """
        if self._command.interactive:
            return await self._run_interactive()
        return await self._run_non_interactive()

    def prepare_outputs_file(self) -> None:
        """Create (or reuse) a temporary file for step output capture.

        Sets ``RUNNER_OUTPUTS`` in the environment so shell commands can
        write ``key=value`` lines that are later parsed by
        :meth:`capture_outputs_file`.
        """
        if not self._command.interactive:
            # Reuse outputs file if already created by StepRunner
            existing = self._envs.get("RUNNER_OUTPUTS")
            if existing:
                self._outputs_file = Path(existing)
            else:
                fd, tmp_path = tempfile.mkstemp(prefix=".tmp_out_", suffix=".txt")
                os.close(fd)
                self._outputs_file = Path(tmp_path)
                self._envs["RUNNER_OUTPUTS"] = str(self._outputs_file)

    async def execute_streaming(
        self,
        on_line: Callable[[str], None] | None = None,
    ) -> CommandExecutionResult:
        """Execute command while streaming stdout line-by-line.

        Each line is passed to *on_line* as it arrives.  The full stdout
        is still collected and returned in the result.
        """
        shell_funcs = get_shell_functions(self._command.shell)
        full_cmd = f"{shell_funcs}\n{self._command.cmd}"

        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            executable=self._command.shell,
            cwd=self._command.working_directory,
            env=self._envs,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )

        stdout_lines: list[str] = []
        stderr_bytes = b""

        async def _read_stdout():
            assert proc.stdout is not None
            async for raw_line in proc.stdout:
                try:
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
                except Exception:
                    line = raw_line.hex()
                stdout_lines.append(line)
                if on_line:
                    try:
                        on_line(line)
                    except Exception as e:
                        logger.debug("on_line callback failed: %s", e)

        async def _read_stderr():
            nonlocal stderr_bytes
            assert proc.stderr is not None
            stderr_bytes = await proc.stderr.read()

        try:
            await asyncio.wait_for(
                asyncio.gather(_read_stdout(), _read_stderr(), proc.wait()),
                self._command.timeout_minutes * 60,
            )
        except TimeoutError:
            _kill_process_tree(proc)
            await proc.wait()
            raise RuntimeError(
                f"Command timed out after {self._command.timeout_minutes} minutes"
            ) from None
        finally:
            self._close_process(proc)

        stdout_str = "\n".join(stdout_lines)
        max_size = settings.max_output_size
        outputs: dict[str, Any] = {}

        if len(stdout_str.encode("utf-8", errors="ignore")) > max_size:
            stdout_str = stdout_str[:max_size] + "\n... [OUTPUT TRUNCATED]"
            outputs["output_truncated"] = True

        try:
            stderr_str = stderr_bytes.decode("utf-8").strip()
        except UnicodeDecodeError:
            stderr_str = base64.b64encode(stderr_bytes).decode("utf-8")

        return CommandExecutionResult(
            exit_code=proc.returncode,
            stdout=stdout_str,
            stderr=stderr_str,
            outputs=outputs,
        )

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
            start_new_session=True,
        )
        try:
            exit_code = await asyncio.wait_for(
                proc.wait(), self._command.timeout_minutes * 60
            )
        except TimeoutError:
            _kill_process_tree(proc)
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
            start_new_session=True,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), self._command.timeout_minutes * 60
            )
            exit_code = proc.returncode
        except TimeoutError:
            _kill_process_tree(proc)
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
        """Raise :class:`RuntimeError` if the exit code indicates failure."""
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
        """Close process transport and streams; ensure the process tree is reaped."""
        pid = proc.pid
        if pid is not None:
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass

        # Close the subprocess transport (owns the underlying pipe fds)
        transport = getattr(proc, "_transport", None)
        if transport is not None:
            try:
                transport.close()
            except Exception as e:
                logger.debug("Failed to close process transport: %s", e)

    async def capture_outputs_file(self, runner, key: str, log_fn) -> None:
        """Parse ``key=value`` lines from the outputs file into the registry.

        The file is deleted after parsing regardless of success or failure.
        """
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
            self._outputs_file.unlink(missing_ok=True)
