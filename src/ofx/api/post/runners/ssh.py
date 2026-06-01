"""SSH-based post-exploitation runner using paramiko."""

from __future__ import annotations

import logging
import os
import secrets
import socket
import tempfile
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from random import uniform

import paramiko  # type: ignore[import-untyped]
from ofx.utils.file_cleanup import remove_file

from ..base import AuthenticationError, ConnectionError, PostRunnerBase, PostRunnerError
from ..registry import RunnerRegistry

__all__ = ["PostSSH"]

logger = logging.getLogger("ofx")


class SSHConnectionError(ConnectionError):
    """SSH connection failed."""


class SSHAuthError(AuthenticationError):
    """SSH authentication failed."""


class SSHTimeoutError(PostRunnerError):
    """SSH command timed out."""


class SSHCommandError(PostRunnerError):
    """Remote command returned non-zero exit code."""

    def __init__(self, message: str, exit_code: int | None = None, stderr: str = ""):
        super().__init__(message, exit_code=exit_code, stderr=stderr)
        self.exit_code = exit_code
        self.stderr = stderr


@RunnerRegistry.register("ssh")
class PostSSH(PostRunnerBase):
    """Post-exploitation runner over SSH via paramiko.

    Features:
    - Key or password authentication (no sshpass dependency)
    - Persistent connection (single TCP connection for all commands)
    - SFTP file transfer (no SCP subprocess)
    - Opsec mode: command-to-file execution (avoids ps visibility)
    - Automatic retries with exponential backoff
    - Command logging for debrief
    - Proxy/jump host support
    - Output-to-file capture for large outputs
    - Context manager support for cleanup

    Args:
        host: Target hostname or IP
        user: SSH username (optional)
        port: SSH port (default: 22)
        identity_file: Path to private key file
        password: SSH password
        connect_timeout: Connection timeout in seconds
        command_timeout: Per-command timeout in seconds (default: 300)
        max_retries: Retry count on transient failures (default: 3)
        max_output_size: Max output bytes before truncation (default: 10MB)
        opsec_mode: Execute commands via temp file on target (avoids ps visibility)
        log_commands: Log all commands/outputs locally
        log_path: Path for command log file
        proxy_command: SSH ProxyCommand for pivoting
        jump_host: SSH jump host for multi-hop (user@host:port)

    Example:
        >>> with PostSSH("192.168.1.100", user="root", opsec_mode=True) as ssh:
        ...     ssh.run("whoami")
        ...     ssh.upload("/tmp/tool", "/tmp/tool")
        'root'
    """

    def __init__(
        self,
        host: str,
        user: str | None = None,
        port: int = 22,
        identity_file: str | None = None,
        password: str | None = None,
        connect_timeout: int = 10,
        command_timeout: int = 300,
        max_retries: int = 3,
        max_output_size: int = 10_000_000,
        opsec_mode: bool = False,
        log_commands: bool = False,
        log_path: str | None = None,
        proxy_command: str | None = None,
        jump_host: str | None = None,
    ):
        self.host = host
        self.user = user
        self.port = port
        self.identity_file = identity_file
        self.password = password
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout
        self.max_retries = max_retries
        self.max_output_size = max_output_size
        self.opsec_mode = opsec_mode
        self.log_commands = log_commands
        self.proxy_command = proxy_command
        self.jump_host = jump_host

        # Paramiko client — lazy-connected
        self._client: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None
        self._jump_client: paramiko.SSHClient | None = None

        # Command log
        self._log_file: Path | None = None
        if log_commands:
            if log_path:
                self._log_file = Path(log_path)
            else:
                fd, log_tmp = tempfile.mkstemp(prefix=".tmp_ssh_", suffix=".log")
                os.close(fd)
                self._log_file = Path(log_tmp)

        # Track temp files on remote for cleanup
        self._remote_temp_files: list[str] = []

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, *exc):
        self.cleanup()

    # -------------------------------------------------------------------------
    # Connection Management
    # -------------------------------------------------------------------------

    def _connect(self) -> paramiko.SSHClient:
        """Establish SSH connection if not already connected."""
        if self._client is not None:
            transport = self._client.get_transport()
            if transport is not None and transport.is_active():
                return self._client
            # Stale connection — reconnect
            self._close_client()

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict = {
            "hostname": self.host,
            "port": self.port,
            "username": self.user,
            "timeout": self.connect_timeout,
            "banner_timeout": self.connect_timeout,
            "auth_timeout": self.connect_timeout,
            "allow_agent": False,
            "look_for_keys": False,
        }

        # Auth
        if self.identity_file:
            try:
                pkey = self._load_key(self.identity_file)
                connect_kwargs["pkey"] = pkey
            except (paramiko.SSHException, OSError, SSHAuthError) as e:
                raise SSHAuthError(
                    f"Failed to load key '{self.identity_file}': {e}"
                ) from e
        elif self.password:
            connect_kwargs["password"] = self.password
        else:
            connect_kwargs["look_for_keys"] = True

        if self.identity_file and self.password:
            connect_kwargs["password"] = self.password

        # Proxy/jump host
        sock = self._create_proxy_sock()
        if sock:
            connect_kwargs["sock"] = sock

        try:
            client.connect(**connect_kwargs)
        except paramiko.AuthenticationException as e:
            raise SSHAuthError(f"SSH auth failed: {e}") from e
        except (TimeoutError, paramiko.SSHException, OSError) as e:
            raise SSHConnectionError(f"SSH connection failed: {e}") from e

        self._client = client
        logger.debug("SSH connected to %s@%s:%d", self.user, self.host, self.port)
        return client

    def _close_client(self) -> None:
        """Close paramiko client, SFTP, and jump host connection."""
        if self._sftp:
            try:
                self._sftp.close()
            except (OSError, paramiko.SSHException) as e:
                logger.debug("SFTP close error: %s", e)
            self._sftp = None
        if self._client:
            try:
                self._client.close()
            except (OSError, paramiko.SSHException) as e:
                logger.debug("SSH client close error: %s", e)
            self._client = None
        if self._jump_client:
            try:
                self._jump_client.close()
            except (OSError, paramiko.SSHException) as e:
                logger.debug("Jump host close error: %s", e)
            self._jump_client = None

    def _get_sftp(self) -> paramiko.SFTPClient:
        """Get or open an SFTP session."""
        if self._sftp is not None:
            try:
                self._sftp.stat(".")
                return self._sftp
            except (OSError, paramiko.SSHException, EOFError):
                logger.debug("SFTP session stale, reconnecting")
                self._sftp = None
        client = self._connect()
        self._sftp = client.open_sftp()
        return self._sftp

    @staticmethod
    def _load_key(path: str) -> paramiko.PKey:
        """Load a private key, trying common formats."""
        path = os.path.expanduser(path)
        for key_class in (
            paramiko.Ed25519Key,
            paramiko.RSAKey,
            paramiko.ECDSAKey,
        ):
            try:
                return key_class.from_private_key_file(path)
            except (paramiko.SSHException, ValueError):
                continue
        raise SSHAuthError(
            f"Cannot load key '{path}': unsupported format or corrupt file"
        )

    def _create_proxy_sock(
        self,
    ) -> paramiko.Channel | socket.socket | paramiko.ProxyCommand | None:
        """Create a proxy socket for ProxyCommand or jump host."""
        if self.proxy_command:
            return paramiko.ProxyCommand(self.proxy_command)

        if self.jump_host:
            # Parse jump_host: user@host:port or host:port or host
            jh = self.jump_host
            jump_user = self.user
            jump_port = 22
            if "@" in jh:
                jump_user, jh = jh.rsplit("@", 1)
            if ":" in jh:
                jh, port_str = jh.rsplit(":", 1)
                with suppress(ValueError):
                    jump_port = int(port_str)
            jump_host = jh

            # Connect to jump host
            jump_client = paramiko.SSHClient()
            jump_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            jump_kwargs: dict = {
                "hostname": jump_host,
                "port": jump_port,
                "username": jump_user,
                "timeout": self.connect_timeout,
                "allow_agent": True,
                "look_for_keys": True,
            }
            if self.password:
                jump_kwargs["password"] = self.password
            if self.identity_file:
                try:
                    jump_kwargs["pkey"] = self._load_key(self.identity_file)
                except (paramiko.SSHException, OSError, SSHAuthError) as e:
                    logger.warning("Failed to load key for jump host: %s", e)
            try:
                jump_client.connect(**jump_kwargs)
                transport = jump_client.get_transport()
                if not transport or not transport.is_active():
                    raise SSHConnectionError(
                        f"Failed to connect to jump host {jump_host}:{jump_port}"
                    )
                self._jump_client = jump_client
                return transport.open_channel(
                    "direct-tcpip",
                    (self.host, self.port),
                    ("127.0.0.1", 0),
                )
            except (paramiko.SSHException, OSError, EOFError):
                with suppress(OSError, paramiko.SSHException):
                    jump_client.close()
                raise

        return None

    # -------------------------------------------------------------------------
    # Command Execution
    # -------------------------------------------------------------------------

    def run(self, command: str, timeout: int | None = None) -> str:
        """Execute a command over SSH with retry logic.

        In opsec_mode, the command is written to a temp file on the target
        and executed from there to avoid visibility in process listings.

        Args:
            command: Shell command to execute.
            timeout: Command timeout in seconds (uses self.command_timeout if None).

        Returns:
            Command stdout output.

        Raises:
            SSHCommandError: If command fails after all retries.
            SSHTimeoutError: If command times out.
            SSHConnectionError: If SSH connection fails.
        """
        if self.opsec_mode:
            return self._run_via_file(command, timeout)
        return self._run_direct(command, timeout)

    def _run_direct(self, command: str, timeout: int | None = None) -> str:
        """Execute command directly over SSH with retries."""
        effective_timeout = timeout or self.command_timeout
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                client = self._connect()
                _, stdout_ch, stderr_ch = client.exec_command(
                    command, timeout=effective_timeout
                )
                exit_code = stdout_ch.channel.recv_exit_status()
                stdout = stdout_ch.read().decode(errors="replace")
                stderr = stderr_ch.read().decode(errors="replace")

                self._log_command(command, stdout, stderr, exit_code)

                if exit_code == 0:
                    if len(stdout) > self.max_output_size:
                        stdout = stdout[: self.max_output_size] + "\n[OUTPUT TRUNCATED]"
                    return stdout

                raise SSHCommandError(
                    stderr.strip() or f"Remote command failed: exit {exit_code}",
                    exit_code=exit_code,
                    stderr=stderr.strip(),
                )

            except SSHCommandError:
                raise
            except SSHAuthError:
                raise
            except paramiko.AuthenticationException as e:
                raise SSHAuthError(f"SSH auth failed: {e}") from e
            except TimeoutError:
                last_error = SSHTimeoutError(
                    f"SSH command timed out after {effective_timeout}s"
                )
                self._close_client()
                if attempt < self.max_retries - 1:
                    delay = min(2**attempt, 30) * uniform(0.5, 1.5)
                    logger.debug(
                        "SSH timeout, retrying in %.1fs (attempt %d/%d)",
                        delay,
                        attempt + 1,
                        self.max_retries,
                    )
                    time.sleep(delay)
                    continue
                raise last_error from None
            except (paramiko.SSHException, OSError, EOFError) as e:
                last_error = SSHConnectionError(f"SSH connection failed: {e}")
                self._close_client()
                if attempt < self.max_retries - 1:
                    delay = min(2**attempt, 30) * uniform(0.5, 1.5)
                    logger.debug(
                        "SSH error, retrying in %.1fs (attempt %d/%d): %s",
                        delay,
                        attempt + 1,
                        self.max_retries,
                        e,
                    )
                    time.sleep(delay)
                    continue

        raise SSHConnectionError(
            f"SSH failed after {self.max_retries} attempts: {last_error}"
        )

    def _run_via_file(self, command: str, timeout: int | None = None) -> str:
        """Execute command via temp file on target (opsec mode).

        Uploads the command as a script via SFTP, executes it, then deletes.
        The actual command is not visible in process listings — only the
        temp file path appears.
        """
        remote_tmp = f"/tmp/.{secrets.token_hex(8)}"
        self._remote_temp_files.append(remote_tmp)

        script_content = f"#!/bin/bash\n{command}\n"

        # Upload script via SFTP (no shell escaping needed)
        sftp = self._get_sftp()
        with sftp.open(remote_tmp, "w") as f:
            f.write(script_content)
        sftp.chmod(remote_tmp, 0o700)

        # Execute and cleanup
        wrapper = f"{remote_tmp}; _rc=$?; rm -f {remote_tmp}; exit $_rc"
        try:
            return self._run_direct(wrapper, timeout)
        finally:
            self._forget_remote_temp_file(remote_tmp)

    def _forget_remote_temp_file(self, remote_tmp: str) -> None:
        if remote_tmp in self._remote_temp_files:
            self._remote_temp_files.remove(remote_tmp)

    def _cleanup_remote_temp_files(self) -> None:
        if not self._remote_temp_files:
            return

        try:
            import shlex

            files = " ".join(shlex.quote(path) for path in self._remote_temp_files)
            self._run_direct(f"rm -f {files}", timeout=10)
        except (OSError, paramiko.SSHException, EOFError) as e:
            logger.warning("Failed to clean remote temp files: %s", e)
        finally:
            self._remote_temp_files.clear()

    def run_with_output_file(self, command: str, timeout: int | None = None) -> str:
        """Execute command and capture output via file (opsec).

        Instead of streaming stdout over SSH, redirects to a temp file
        on the remote, downloads it via SFTP, and deletes. Avoids large
        output on the SSH wire (detectable by DPI).

        Args:
            command: Shell command to execute.
            timeout: Command timeout in seconds.

        Returns:
            Command output from the captured file.
        """
        remote_out = f"/tmp/.{secrets.token_hex(8)}"
        self._remote_temp_files.append(remote_out)

        wrapped = f"({command}) > {remote_out} 2>&1; echo $?"
        self._run_direct(wrapped, timeout)

        # Download via SFTP
        fd, local_tmp = tempfile.mkstemp(prefix=".tmp_dl_")
        os.close(fd)
        try:
            sftp = self._get_sftp()
            sftp.get(remote_out, local_tmp)
            output = Path(local_tmp).read_text()
            if len(output) > self.max_output_size:
                output = output[: self.max_output_size] + "\n[OUTPUT TRUNCATED]"
        finally:
            remove_file(local_tmp)
            try:
                self._run_direct(f"rm -f {remote_out}", timeout=10)
            except (OSError, paramiko.SSHException, EOFError) as e:
                logger.debug("Failed to remove remote output file: %s", e)

        return output

    # -------------------------------------------------------------------------
    # File Transfer (SFTP)
    # -------------------------------------------------------------------------

    def _sftp_with_retry(
        self, operation: str, sftp_fn: str, src: str, dst: str
    ) -> None:
        """Execute an SFTP operation with retry logic.

        Args:
            operation: Human-readable label (``"UPLOAD"`` or ``"DOWNLOAD"``).
            sftp_fn: SFTP method name (``"put"`` or ``"get"``).
            src: Source path (first arg to the SFTP method).
            dst: Destination path (second arg to the SFTP method).
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                sftp = self._get_sftp()
                getattr(sftp, sftp_fn)(src, dst)
                self._log_command(
                    f"[SFTP {operation}] {src} -> {dst}",
                    "OK",
                    "",
                    0,
                )
                return
            except paramiko.AuthenticationException as e:
                raise SSHAuthError(f"SFTP auth failed: {e}") from e
            except (paramiko.SSHException, OSError, EOFError) as e:
                last_error = e
                self._sftp = None
                self._close_client()
                if attempt < self.max_retries - 1:
                    delay = min(2**attempt, 30) * uniform(0.5, 1.5)
                    logger.debug(
                        "SFTP %s error, retrying in %.1fs (attempt %d/%d): %s",
                        operation.lower(),
                        delay,
                        attempt + 1,
                        self.max_retries,
                        e,
                    )
                    time.sleep(delay)

        raise SSHConnectionError(
            f"SFTP {operation.lower()} failed after {self.max_retries} attempts: {last_error}"
        )

    def upload(
        self, local_path: str, remote_path: str, timeout: int | None = None
    ) -> None:
        """Upload a file via SFTP with retry logic.

        Args:
            local_path: Local file path.
            remote_path: Remote destination path.
            timeout: Ignored (SFTP doesn't have per-op timeout). Kept for compat.
        """
        self._sftp_with_retry("UPLOAD", "put", local_path, remote_path)

    def download(
        self, remote_path: str, local_path: str, timeout: int | None = None
    ) -> None:
        """Download a file via SFTP with retry logic.

        Args:
            remote_path: Remote file path.
            local_path: Local destination path.
            timeout: Ignored (SFTP doesn't have per-op timeout). Kept for compat.
        """
        try:
            self._sftp_with_retry("DOWNLOAD", "get", remote_path, local_path)
        except Exception:
            # Remove partial file left by a failed transfer
            remove_file(local_path)
            raise

    # -------------------------------------------------------------------------
    # Interactive Shell
    # -------------------------------------------------------------------------

    def supports_interactive(self) -> bool:
        return True

    def interactive_shell(self, **kwargs) -> None:
        """Start an interactive SSH shell session.

        Falls back to subprocess ssh for true terminal interactivity,
        since paramiko channels don't attach to the local TTY natively.
        """
        import subprocess

        cmd = ["ssh", "-p", str(self.port)]
        cmd.extend(["-o", "StrictHostKeyChecking=no"])
        cmd.extend(["-o", "UserKnownHostsFile=/dev/null"])
        if self.identity_file:
            cmd.extend(["-i", self.identity_file])
            cmd.extend(["-o", "IdentitiesOnly=yes"])
        target = f"{self.user}@{self.host}" if self.user else self.host
        cmd.append(target)
        subprocess.run(cmd, check=False)

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------

    @staticmethod
    def _sanitize_for_log(text: str) -> str:
        """Redact common credential patterns from text before logging."""
        import re

        # URL credentials: https://user:pass@host
        text = re.sub(r"(https?://[^:]+:)[^\s@]+(@)", r"\1***\2", text)
        # Key=value patterns: password=secret, token=abc, key=xyz
        text = re.sub(
            r"((?:password|passwd|token|secret|api_key|apikey|auth|credential|jwt)=)[^\s&\"']+",
            r"\1***",
            text,
            flags=re.IGNORECASE,
        )
        # Flag patterns: --password secret, --token secret (only for known flags)
        text = re.sub(
            r"(--(?:password|passwd|token|secret|api-key)\s+)\S+",
            r"\1***",
            text,
            flags=re.IGNORECASE,
        )
        return text

    def _log_command(
        self, command: str, stdout: str, stderr: str, returncode: int
    ) -> None:
        """Log a command execution to the local log file."""
        if not self.log_commands or not self._log_file:
            return

        sanitized_cmd = self._sanitize_for_log(command)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] host={self.host} rc={returncode}\nCMD: {sanitized_cmd}\n"
        if stdout:
            entry += f"STDOUT:\n{stdout[:5000]}\n"
        if stderr:
            entry += f"STDERR:\n{stderr[:2000]}\n"
        entry += "---\n"

        try:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            with self._log_file.open("a") as f:
                f.write(entry)
        except OSError as e:
            logger.warning("Failed to write command log: %s", e)

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    def cleanup(self) -> None:
        """Clean up remote temp files and close connection."""
        self._cleanup_remote_temp_files()

        self._close_client()
        logger.debug("SSH cleanup completed for %s", self.host)
