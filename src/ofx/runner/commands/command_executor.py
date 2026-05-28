"""Command execution helper for subprocess handling."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import signal
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ofx.models.command import Command
from ofx.runner.commands.shell_functions import get_shell_functions
from ofx.settings import settings

logger = logging.getLogger("ofx")

RUNNER_OUTPUTS_ENV = "RUNNER_OUTPUTS"
OFX_OUTPUTS_ENV = "OFX_OUTPUTS"


@dataclass
class CommandExecutionResult:
    exit_code: int | None
    stdout: str
    stderr: str
    outputs: dict[str, Any]


def parse_outputs_file(
    outputs_file: Path,
    log_fn: Callable[[str], None],
) -> dict[str, str]:
    """Parse and remove a RUNNER_OUTPUTS-style ``key=value`` file."""
    parsed: dict[str, str] = {}
    if not outputs_file.exists():
        return parsed
    try:
        outputs_content = outputs_file.read_text().strip()
        if outputs_content:
            for line in outputs_content.splitlines():
                line = line.strip()
                if line and "=" in line:
                    key_name, value = line.split("=", 1)
                    key_name = key_name.strip()
                    value = value.strip()
                    if key_name:
                        parsed[key_name] = value
                        log_fn(f"Captured output: {key_name}={value}")
    except Exception as e:
        log_fn(f"Failed to parse RUNNER_OUTPUTS: {e}")
    finally:
        try:
            outputs_file.unlink(missing_ok=True)
        except Exception as e:
            log_fn(f"Failed to remove outputs file: {e}")
    return parsed


def prepare_outputs_file_env(
    envs: dict[str, Any],
    *,
    interactive: bool,
    include_ofx_alias: bool = False,
) -> Path | None:
    """Create or reuse the outputs file path injected into a command environment."""
    if interactive:
        return None

    existing = envs.get(RUNNER_OUTPUTS_ENV)
    if existing:
        outputs_file = Path(existing)
    else:
        from ofx.utils.tempfiles import make_temp_file

        outputs_file = make_temp_file(prefix=".tmp_out_")
        envs[RUNNER_OUTPUTS_ENV] = str(outputs_file)

    if include_ofx_alias:
        envs[OFX_OUTPUTS_ENV] = str(outputs_file)

    return outputs_file


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
    with suppress(OSError, ProcessLookupError):
        os.killpg(pgid, signal.SIGTERM)

    # Give children 2 seconds to exit, then force-kill
    import time

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)  # probe
        except (OSError, ProcessLookupError):
            return  # all dead
        time.sleep(0.1)

    with suppress(OSError, ProcessLookupError):
        os.killpg(pgid, signal.SIGKILL)


class CommandExecutor:
    """Handles subprocess execution for CommandRunner."""

    def __init__(self, command: Command, envs: dict[str, Any]) -> None:
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
        self._outputs_file = prepare_outputs_file_env(
            self._envs,
            interactive=self._command.interactive,
        )

    async def execute_streaming(
        self,
        on_line: Callable[[str], None] | None = None,
    ) -> CommandExecutionResult:
        """Execute command while streaming stdout line-by-line.

        Each line is passed to *on_line* as it arrives.  The full stdout
        is still collected and returned in the result.
        """
        # Raise the StreamReader line-buffer limit to 10 MB.
        # The default 64 KB causes "Separator is not found, and chunk exceed
        # the limit" errors when tools like katana emit long JSONL lines.
        _STREAM_LIMIT = 10 * 1024 * 1024  # 10 MB

        proc = await asyncio.create_subprocess_shell(
            self._full_command(),
            executable=self._command.shell,
            cwd=self._command.working_directory,
            env=self._envs,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            limit=_STREAM_LIMIT,
        )

        stdout_lines: list[str] = []
        stderr_bytes = b""
        stdout_bytes_total = 0

        async def _read_stdout():
            nonlocal stdout_bytes_total
            assert proc.stdout is not None
            max_size = settings.max_output_size
            try:
                async for raw_line in proc.stdout:
                    try:
                        line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
                    except Exception as e:
                        logger.debug("Failed to decode stdout line as UTF-8, using hex: %s", e)
                        line = raw_line.hex()
                    stdout_bytes_total += len(raw_line)
                    if stdout_bytes_total <= max_size:
                        stdout_lines.append(line)
                    if on_line:
                        try:
                            on_line(line)
                        except Exception as e:
                            logger.debug("on_line callback failed: %s", e)
            except ValueError as e:
                # asyncio raises ValueError("Separator is not found, and chunk
                # exceed the limit") when a single line exceeds the StreamReader
                # buffer limit even after we raised it. Log and stop reading
                # rather than crashing the whole task.
                logger.debug("stdout readline limit exceeded, stopping stream: %s", e)

        async def _read_stderr():
            nonlocal stderr_bytes
            assert proc.stderr is not None
            stderr_bytes = await proc.stderr.read()

        try:
            await asyncio.wait_for(
                asyncio.gather(_read_stdout(), _read_stderr(), proc.wait()),
                self._command.timeout_minutes * 60,
            )
        except TimeoutError as te:
            _kill_process_tree(proc)
            await proc.wait()
            raise RuntimeError(
                f"Command timed out after {self._command.timeout_minutes} minutes"
            ) from te
        finally:
            self._close_process(proc)

        stdout_str = "\n".join(stdout_lines)
        max_size = settings.max_output_size
        outputs: dict[str, Any] = {}

        if stdout_bytes_total > max_size:
            stdout_str += "\n... [OUTPUT TRUNCATED]"
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
        proc = await asyncio.create_subprocess_shell(
            self._full_command(),
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
        except TimeoutError as te:
            _kill_process_tree(proc)
            await proc.wait()
            raise RuntimeError(
                f"Command timed out after {self._command.timeout_minutes} minutes"
            ) from te
        finally:
            self._close_process(proc)

        return CommandExecutionResult(
            exit_code=exit_code,
            stdout="[Interactive mode - output shown in real-time]",
            stderr="",
            outputs={},
        )

    async def _run_non_interactive(self) -> CommandExecutionResult:
        proc = await asyncio.create_subprocess_shell(
            self._full_command(),
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
        except TimeoutError as te:
            _kill_process_tree(proc)
            await proc.wait()
            raise RuntimeError(
                f"Command timed out after {self._command.timeout_minutes} minutes"
            ) from te
        finally:
            self._close_process(proc)

        stdout, stderr, outputs = self._decode_output(stdout_bytes, stderr_bytes)
        return CommandExecutionResult(
            exit_code=exit_code, stdout=stdout, stderr=stderr, outputs=outputs
        )

    def _full_command(self) -> str:
        """Return the command with shell helper functions prepended."""
        return f"{get_shell_functions(self._command.shell)}\n{self._command.cmd}"

    def _decode_output(
        self, stdout_bytes: bytes, stderr_bytes: bytes
    ) -> tuple[str, str, dict[str, Any]]:
        max_size = settings.max_output_size
        outputs: dict[str, Any] = {}
        try:
            stdout = self._decode_utf8_output(
                stdout_bytes,
                max_size=max_size,
                truncated_suffix="\n... [OUTPUT TRUNCATED]",
                truncated_flag="output_truncated",
                outputs=outputs,
            )
            stderr = self._decode_utf8_output(
                stderr_bytes,
                max_size=max_size,
                truncated_suffix="\n... [STDERR TRUNCATED]",
                truncated_flag="stderr_truncated",
                outputs=outputs,
            )

        except UnicodeDecodeError:
            outputs["binary_output"] = True
            stdout = self._encode_binary_output(
                stdout_bytes,
                max_size=max_size,
                truncated_suffix="... [BINARY OUTPUT TRUNCATED]",
                truncated_flag="output_truncated",
                outputs=outputs,
            )
            stderr = self._encode_binary_output(
                stderr_bytes,
                max_size=max_size,
                truncated_suffix="... [BINARY STDERR TRUNCATED]",
                truncated_flag="stderr_truncated",
                outputs=outputs,
            )

        return stdout, stderr, outputs

    @staticmethod
    def _decode_utf8_output(
        output_bytes: bytes,
        *,
        max_size: int,
        truncated_suffix: str,
        truncated_flag: str,
        outputs: dict[str, Any],
    ) -> str:
        text = output_bytes.decode("utf-8").strip()
        if len(output_bytes) > max_size:
            text = output_bytes[:max_size].decode("utf-8", errors="ignore") + truncated_suffix
            outputs[truncated_flag] = True
        return text

    @staticmethod
    def _encode_binary_output(
        output_bytes: bytes,
        *,
        max_size: int,
        truncated_suffix: str,
        truncated_flag: str,
        outputs: dict[str, Any],
    ) -> str:
        if len(output_bytes) > max_size:
            outputs[truncated_flag] = True
            return base64.b64encode(output_bytes[:max_size]).decode("utf-8") + truncated_suffix
        return base64.b64encode(output_bytes).decode("utf-8")

    def raise_for_status(self, exit_code: int | None, stderr: str) -> None:
        """Raise :class:`RuntimeError` if the exit code indicates failure."""
        if self._command.interactive:
            if exit_code not in (0, 130, 127):
                stderr = stderr or f"Command failed with exit code {exit_code}"
                raise RuntimeError(f"Command failed: {stderr}")
            return
        if exit_code != 0:
            stderr = stderr or f"Command failed with exit code {exit_code}"
            raise RuntimeError(f"Command failed: {stderr}")

    @staticmethod
    def _close_process(proc: asyncio.subprocess.Process) -> None:
        """Close process transport and streams; ensure the process tree is reaped."""
        pid = proc.pid
        if pid is not None:
            with suppress(OSError, ProcessLookupError):
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)

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
        if not self._outputs_file:
            return
        for key_name, value in parse_outputs_file(self._outputs_file, log_fn).items():
            await runner.reg_update(key, {key_name: value})
