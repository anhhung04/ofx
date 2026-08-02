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
from ofx.utils.file_cleanup import remove_file
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
        for line in outputs_file.read_text().splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            key_name, value = line.split("=", 1)
            key_name = key_name.strip()
            value = value.strip()
            if not key_name:
                continue
            parsed[key_name] = value
            log_fn(f"Captured output: {key_name}={value}")
    except Exception as e:
        log_fn(f"Failed to parse RUNNER_OUTPUTS: {e}")
    finally:
        exc = remove_file(outputs_file)
        if exc is not None:
            log_fn(f"Failed to remove outputs file: {exc}")
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

def _reap_process_group(pgid: int) -> None:
    """Reap all zombie processes in a process group to prevent orphans.

    After killing a process group, child processes remain as zombies
    until the parent calls ``waitpid()``.  This function reaps them
    with ``WNOHANG`` so the call never blocks.
    """
    try:
        while True:
            wpid, _status = os.waitpid(-pgid, os.WNOHANG)
            if wpid == 0:
                break
    except ChildProcessError:
        pass


def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    """Send SIGTERM to the process group, then SIGKILL if still alive.

    When subprocesses are launched with ``start_new_session=True`` the
    child becomes the session leader.  Sending a signal to the negative
    PID targets the entire process group so that grandchildren (e.g.
    nmap spawned by bash) are also cleaned up.

    After every kill, zombie processes are reaped so the process table
    stays clean and no orphans are left behind.
    """
    pgid = _process_group_id(proc)
    if pgid is None:
        return

    with suppress(OSError, ProcessLookupError):
        os.killpg(pgid, signal.SIGTERM)

    import time

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except (OSError, ProcessLookupError):
            _reap_process_group(pgid)
            return
        time.sleep(0.1)

    try:
        os.killpg(pgid, 0)
    except (OSError, ProcessLookupError):
        _reap_process_group(pgid)
        return

    with suppress(OSError, ProcessLookupError):
        os.killpg(pgid, signal.SIGKILL)

    _reap_process_group(pgid)

def _process_group_id(proc: asyncio.subprocess.Process) -> int | None:
    pid = proc.pid
    if pid is None:
        return None

    try:
        return os.getpgid(pid)
    except (OSError, ProcessLookupError):
        return None

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

    async def _spawn_subprocess(self, **overrides: Any) -> asyncio.subprocess.Process:
        kwargs: dict[str, Any] = {
            "executable": self._command.shell,
            "cwd": self._command.working_directory,
            "env": self._envs,
            "start_new_session": True,
        }
        kwargs.update(overrides)
        return await asyncio.create_subprocess_shell(
            f"{get_shell_functions(self._command.shell)}\n{self._command.cmd}",
            **kwargs,
        )

    async def _await_with_timeout(self, proc, awaitable) -> Any:
        try:
            return await asyncio.wait_for(awaitable, self._command.timeout_minutes * 60)
        except TimeoutError as te:
            _kill_process_tree(proc)
            await proc.wait()
            raise RuntimeError(
                f"Command timed out after {self._command.timeout_minutes} minutes"
            ) from te
        finally:
            pgid = _process_group_id(proc)
            if pgid is not None:
                with suppress(OSError, ProcessLookupError):
                    os.killpg(pgid, signal.SIGTERM)

            transport = getattr(proc, "_transport", None)
            if transport is not None:
                try:
                    transport.close()
                except Exception as e:
                    logger.debug("Failed to close process transport: %s", e)

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
        _STREAM_LIMIT = 10 * 1024 * 1024

        proc = await self._spawn_subprocess(
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
                    if on_line is not None:
                        try:
                            on_line(line)
                        except Exception as e:
                            logger.debug("on_line callback failed: %s", e)
            except ValueError as e:
                logger.debug("stdout readline limit exceeded, stopping stream: %s", e)

        async def _read_stderr():
            nonlocal stderr_bytes
            assert proc.stderr is not None
            stderr_bytes = await proc.stderr.read()

        await self._await_with_timeout(
            proc,
            asyncio.gather(_read_stdout(), _read_stderr(), proc.wait()),
        )
        try:
            stderr = stderr_bytes.decode("utf-8").strip()
        except UnicodeDecodeError:
            stderr = base64.b64encode(stderr_bytes).decode("utf-8")

        outputs: dict[str, Any] = {}
        stdout = "\n".join(stdout_lines)
        if stdout_bytes_total > settings.max_output_size:
            stdout += "\n... [OUTPUT TRUNCATED]"
            outputs["output_truncated"] = True

        return CommandExecutionResult(
            exit_code=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            outputs=outputs or {},
        )

    async def _run_interactive(self) -> CommandExecutionResult:
        proc = await self._spawn_subprocess(
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        exit_code = await self._await_with_timeout(proc, proc.wait())
        return CommandExecutionResult(
            exit_code=exit_code,
            stdout="[Interactive mode - output shown in real-time]",
            stderr="",
            outputs={},
        )

    async def _run_non_interactive(self) -> CommandExecutionResult:
        proc = await self._spawn_subprocess(
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await self._await_with_timeout(proc, proc.communicate())
        stdout, stderr, outputs = self._decode_output(stdout_bytes, stderr_bytes)
        return CommandExecutionResult(
            exit_code=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            outputs=outputs or {},
        )

    def _decode_output(
        self, stdout_bytes: bytes, stderr_bytes: bytes
    ) -> tuple[str, str, dict[str, Any]]:
        max_size = settings.max_output_size
        outputs: dict[str, Any] = {}

        try:
            stdout = stdout_bytes.decode("utf-8").strip()
            if len(stdout_bytes) > max_size:
                outputs["output_truncated"] = True
                stdout = (
                    stdout_bytes[:max_size].decode("utf-8", errors="ignore")
                    + "\n... [OUTPUT TRUNCATED]"
                )

            stderr = stderr_bytes.decode("utf-8").strip()
            if len(stderr_bytes) > max_size:
                outputs["stderr_truncated"] = True
                stderr = (
                    stderr_bytes[:max_size].decode("utf-8", errors="ignore")
                    + "\n... [STDERR TRUNCATED]"
                )
        except UnicodeDecodeError:
            outputs["binary_output"] = True
            stdout = base64.b64encode(stdout_bytes).decode("utf-8")
            if len(stdout_bytes) > max_size:
                outputs["output_truncated"] = True
                stdout = (
                    base64.b64encode(stdout_bytes[:max_size]).decode("utf-8")
                    + "... [BINARY OUTPUT TRUNCATED]"
                )

            stderr = base64.b64encode(stderr_bytes).decode("utf-8")
            if len(stderr_bytes) > max_size:
                outputs["stderr_truncated"] = True
                stderr = (
                    base64.b64encode(stderr_bytes[:max_size]).decode("utf-8")
                    + "... [BINARY STDERR TRUNCATED]"
                )

        return stdout, stderr, outputs

    async def capture_outputs_file(self, runner, key: str, log_fn) -> None:
        """Parse ``key=value`` lines from the outputs file into the registry.

        The file is deleted after parsing regardless of success or failure.
        """
        if self._outputs_file is None:
            return
        outputs = parse_outputs_file(self._outputs_file, log_fn)
        if outputs:
            await runner.reg_update(key, outputs)
