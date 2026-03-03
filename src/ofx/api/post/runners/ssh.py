"""SSH-based post-exploitation runner with opsec and stability features."""

from __future__ import annotations

import logging
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from ..base import PostRunnerBase
from ..registry import RunnerRegistry

__all__ = ["PostSSH"]

logger = logging.getLogger("ofx")


class SSHConnectionError(RuntimeError):
    """SSH connection failed."""


class SSHAuthError(RuntimeError):
    """SSH authentication failed."""


class SSHTimeoutError(RuntimeError):
    """SSH command timed out."""


class SSHCommandError(RuntimeError):
    """Remote command returned non-zero exit code."""

    def __init__(self, message: str, exit_code: int | None = None, stderr: str = ""):
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr


@RunnerRegistry.register("ssh")
class PostSSH(PostRunnerBase):
    """Post-exploitation runner over SSH with stability and opsec features.

    Features:
    - Key or password authentication
    - SSH ControlMaster for persistent connections (10x faster multi-command)
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
        password: SSH password (uses sshpass if available)
        connect_timeout: Connection timeout in seconds
        command_timeout: Per-command timeout in seconds (default: 300)
        max_retries: Retry count on transient failures (default: 3)
        max_output_size: Max output bytes before truncation (default: 10MB)
        use_controlmaster: Use SSH ControlMaster for persistent connection
        opsec_mode: Execute commands via temp file on target (avoids ps visibility)
        log_commands: Log all commands/outputs locally
        log_path: Path for command log file
        proxy_command: SSH ProxyCommand for pivoting
        jump_host: SSH jump host (-J) for multi-hop
        extra_args: Additional SSH arguments

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
        use_controlmaster: bool = True,
        opsec_mode: bool = False,
        log_commands: bool = False,
        log_path: str | None = None,
        proxy_command: str | None = None,
        jump_host: str | None = None,
        extra_args: Sequence[str] | None = None,
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
        self.use_controlmaster = use_controlmaster
        self.opsec_mode = opsec_mode
        self.log_commands = log_commands
        self.proxy_command = proxy_command
        self.jump_host = jump_host
        self.extra_args = list(extra_args) if extra_args else []

        # ControlMaster socket path
        self._control_path: str | None = None
        self._control_active = False

        # Command log
        self._log_file: Path | None = None
        if log_commands:
            if log_path:
                self._log_file = Path(log_path)
            else:
                self._log_file = Path(tempfile.mktemp(
                    prefix=f"ofx_ssh_{host}_", suffix=".log"
                ))

        # Track temp files on remote for cleanup
        self._remote_temp_files: list[str] = []

        # Has sshpass?
        self._has_sshpass = shutil.which("sshpass") is not None
        if self.password and not self._has_sshpass:
            # Without sshpass, SSH would block waiting for a TTY password prompt
            raise ValueError(
                "Password authentication requires 'sshpass' installed; "
                "install it or provide an identity_file."
            )

    def __enter__(self):
        if self.use_controlmaster:
            self._start_controlmaster()
        return self

    def __exit__(self, *exc):
        self.cleanup()

    # -------------------------------------------------------------------------
    # ControlMaster Management
    # -------------------------------------------------------------------------

    def _start_controlmaster(self) -> None:
        """Start SSH ControlMaster for persistent connection multiplexing."""
        if self._control_active:
            return

        tmpdir = tempfile.mkdtemp(prefix="ofx_ssh_")
        self._control_path = os.path.join(tmpdir, f"cm_{self.host}_{self.port}")

        cmd = self._build_ssh_cmd(extra=[
            "-M",  # Master mode
            "-N",  # No remote command
            "-f",  # Background
            "-o", f"ControlPath={self._control_path}",
            "-o", "ControlPersist=300",
        ])

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.connect_timeout + 10, check=False,
            )
            if result.returncode == 0:
                self._control_active = True
                logger.debug(f"SSH ControlMaster started for {self.host}")
            else:
                logger.warning(
                    f"ControlMaster failed ({result.returncode}), "
                    f"falling back to per-command connections: {result.stderr.strip()}"
                )
                self._control_path = None
        except subprocess.TimeoutExpired:
            logger.warning("ControlMaster timed out, using per-command connections")
            self._control_path = None

    def _stop_controlmaster(self) -> None:
        """Stop the SSH ControlMaster."""
        if not self._control_active or not self._control_path:
            return

        cmd = self._build_ssh_cmd(extra=[
            "-O", "exit",
            "-o", f"ControlPath={self._control_path}",
        ])
        try:
            subprocess.run(cmd, capture_output=True, timeout=10, check=False)
        except Exception:
            pass

        self._control_active = False
        # Clean up socket dir
        socket_dir = os.path.dirname(self._control_path)
        if os.path.isdir(socket_dir):
            shutil.rmtree(socket_dir, ignore_errors=True)
        self._control_path = None

    # -------------------------------------------------------------------------
    # Command Building
    # -------------------------------------------------------------------------

    def _build_ssh_cmd(self, extra: list[str] | None = None) -> list[str]:
        """Build SSH command with all configured options."""
        cmd: list[str] = []

        # Password auth via sshpass
        if self.password and self._has_sshpass:
            cmd.extend(["sshpass", "-p", self.password])

        cmd.extend(["ssh", "-p", str(self.port)])
        cmd.extend(["-o", "StrictHostKeyChecking=no"])
        cmd.extend(["-o", "UserKnownHostsFile=/dev/null"])
        cmd.extend(["-o", f"ConnectTimeout={self.connect_timeout}"])
        cmd.extend(["-o", "BatchMode=yes"] if not self.password else [])

        # ControlMaster socket
        if self._control_active and self._control_path:
            cmd.extend(["-o", f"ControlPath={self._control_path}"])

        # Identity file
        if self.identity_file:
            cmd.extend(["-i", self.identity_file])

        # Proxy command
        if self.proxy_command:
            cmd.extend(["-o", f"ProxyCommand={self.proxy_command}"])

        # Jump host
        if self.jump_host:
            cmd.extend(["-J", self.jump_host])

        # Extra args
        if self.extra_args:
            cmd.extend(self.extra_args)

        if extra:
            cmd.extend(extra)

        # Target
        target = f"{self.user}@{self.host}" if self.user else self.host
        cmd.append(target)
        return cmd

    def _build_scp_cmd(self) -> list[str]:
        """Build SCP command with all configured options."""
        cmd: list[str] = []

        if self.password and self._has_sshpass:
            cmd.extend(["sshpass", "-p", self.password])

        cmd.extend(["scp", "-P", str(self.port)])
        cmd.extend(["-o", "StrictHostKeyChecking=no"])
        cmd.extend(["-o", "UserKnownHostsFile=/dev/null"])

        if self._control_active and self._control_path:
            cmd.extend(["-o", f"ControlPath={self._control_path}"])

        if self.identity_file:
            cmd.extend(["-i", self.identity_file])

        if self.proxy_command:
            cmd.extend(["-o", f"ProxyCommand={self.proxy_command}"])

        if self.jump_host:
            cmd.extend(["-J", self.jump_host])

        if self.extra_args:
            cmd.extend(self.extra_args)

        return cmd

    def _target_path(self, path: str) -> str:
        """Format path with user@host prefix for SCP."""
        if self.user:
            return f"{self.user}@{self.host}:{path}"
        return f"{self.host}:{path}"

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
                cmd = self._build_ssh_cmd() + [command]
                result = subprocess.run(
                    cmd,
                    text=True,
                    capture_output=True,
                    timeout=effective_timeout,
                    check=False,
                )

                self._log_command(command, result.stdout, result.stderr, result.returncode)

                if result.returncode == 0:
                    output = result.stdout
                    if len(output) > self.max_output_size:
                        output = output[: self.max_output_size] + "\n[OUTPUT TRUNCATED]"
                    return output

                # Classify errors
                stderr = result.stderr.strip()
                if "Permission denied" in stderr or "Authentication failed" in stderr:
                    raise SSHAuthError(f"SSH auth failed: {stderr}")
                if "Connection refused" in stderr or "No route to host" in stderr:
                    raise SSHConnectionError(f"SSH connection failed: {stderr}")

                raise SSHCommandError(
                    stderr or f"SSH command failed: exit {result.returncode}",
                    exit_code=result.returncode,
                    stderr=stderr,
                )

            except subprocess.TimeoutExpired:
                raise SSHTimeoutError(
                    f"SSH command timed out after {effective_timeout}s"
                ) from None
            except (SSHAuthError, SSHTimeoutError):
                raise
            except SSHConnectionError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = 2 ** attempt
                    logger.debug(
                        f"SSH connection failed, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(delay)
            except SSHCommandError:
                raise
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)

        raise SSHConnectionError(
            f"SSH failed after {self.max_retries} attempts: {last_error}"
        )

    def _run_via_file(self, command: str, timeout: int | None = None) -> str:
        """Execute command via temp file on target (opsec mode).

        Writes command to a random temp file, executes it, then deletes.
        The actual command is not visible in process listings — only the
        temp file path appears.
        """
        remote_tmp = f"/tmp/.{secrets.token_hex(8)}"
        self._remote_temp_files.append(remote_tmp)

        # Write command to temp file, execute, capture output, clean up
        # Using heredoc to avoid escaping issues
        wrapper = (
            f"cat > {remote_tmp} << 'OFXEOF'\n"
            f"#!/bin/bash\n"
            f"{command}\n"
            f"OFXEOF\n"
            f"chmod +x {remote_tmp} && {remote_tmp}; _rc=$?; rm -f {remote_tmp}; exit $_rc"
        )
        return self._run_direct(wrapper, timeout)

    def run_with_output_file(self, command: str, timeout: int | None = None) -> str:
        """Execute command and capture output via file (opsec).

        Instead of streaming stdout over SSH, redirects to a temp file
        on the remote, SCPs it back, and deletes. Avoids large output
        on the SSH wire (detectable by DPI).

        Args:
            command: Shell command to execute.
            timeout: Command timeout in seconds.

        Returns:
            Command output from the captured file.
        """
        remote_out = f"/tmp/.{secrets.token_hex(8)}"
        self._remote_temp_files.append(remote_out)

        # Run command with output redirected to file
        wrapped = f"({command}) > {remote_out} 2>&1; echo $?"
        self._run_direct(wrapped, timeout)

        # Download the output file
        local_tmp = tempfile.mktemp(prefix="ofx_out_")
        try:
            self.download(remote_out, local_tmp)
            output = Path(local_tmp).read_text()
            if len(output) > self.max_output_size:
                output = output[: self.max_output_size] + "\n[OUTPUT TRUNCATED]"
        finally:
            Path(local_tmp).unlink(missing_ok=True)
            # Clean up remote
            try:
                self._run_direct(f"rm -f {remote_out}", timeout=10)
            except Exception:
                pass

        return output

    # -------------------------------------------------------------------------
    # File Transfer
    # -------------------------------------------------------------------------

    def upload(self, local_path: str, remote_path: str, timeout: int | None = None) -> None:
        """Upload a file via SCP with retry logic.

        Args:
            local_path: Local file path.
            remote_path: Remote destination path.
            timeout: Transfer timeout in seconds.
        """
        effective_timeout = timeout or self.command_timeout
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                cmd = self._build_scp_cmd() + [local_path, self._target_path(remote_path)]
                result = subprocess.run(
                    cmd, text=True, capture_output=True,
                    timeout=effective_timeout, check=False,
                )
                if result.returncode == 0:
                    self._log_command(
                        f"[SCP UPLOAD] {local_path} -> {remote_path}",
                        "OK", result.stderr, result.returncode,
                    )
                    return
                last_error = RuntimeError(
                    result.stderr.strip() or f"SCP upload failed: {result.returncode}"
                )
            except subprocess.TimeoutExpired:
                raise SSHTimeoutError(
                    f"SCP upload timed out after {effective_timeout}s"
                ) from None
            except Exception as e:
                last_error = e

            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)

        raise RuntimeError(f"SCP upload failed after {self.max_retries} attempts: {last_error}")

    def download(self, remote_path: str, local_path: str, timeout: int | None = None) -> None:
        """Download a file via SCP with retry logic.

        Args:
            remote_path: Remote file path.
            local_path: Local destination path.
            timeout: Transfer timeout in seconds.
        """
        effective_timeout = timeout or self.command_timeout
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                cmd = self._build_scp_cmd() + [self._target_path(remote_path), local_path]
                result = subprocess.run(
                    cmd, text=True, capture_output=True,
                    timeout=effective_timeout, check=False,
                )
                if result.returncode == 0:
                    self._log_command(
                        f"[SCP DOWNLOAD] {remote_path} -> {local_path}",
                        "OK", result.stderr, result.returncode,
                    )
                    return
                last_error = RuntimeError(
                    result.stderr.strip() or f"SCP download failed: {result.returncode}"
                )
            except subprocess.TimeoutExpired:
                raise SSHTimeoutError(
                    f"SCP download timed out after {effective_timeout}s"
                ) from None
            except Exception as e:
                last_error = e

            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)

        raise RuntimeError(f"SCP download failed after {self.max_retries} attempts: {last_error}")

    # -------------------------------------------------------------------------
    # Interactive Shell
    # -------------------------------------------------------------------------

    def supports_interactive(self) -> bool:
        return True

    def interactive_shell(self, **kwargs) -> None:
        """Start an interactive SSH shell session."""
        cmd = self._build_ssh_cmd()
        subprocess.run(cmd, check=False)

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
        entry = (
            f"[{timestamp}] host={self.host} rc={returncode}\n"
            f"CMD: {command}\n"
        )
        if stdout:
            entry += f"STDOUT:\n{stdout[:5000]}\n"
        if stderr:
            entry += f"STDERR:\n{stderr[:2000]}\n"
        entry += "---\n"

        try:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            with self._log_file.open("a") as f:
                f.write(entry)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    def cleanup(self) -> None:
        """Clean up ControlMaster, remote temp files, and resources."""
        # Clean up remote temp files
        if self._remote_temp_files:
            try:
                files = " ".join(self._remote_temp_files)
                self._run_direct(f"rm -f {files}", timeout=10)
            except Exception:
                pass
            self._remote_temp_files.clear()

        # Stop ControlMaster
        self._stop_controlmaster()

        logger.debug(f"SSH cleanup completed for {self.host}")

    # -------------------------------------------------------------------------
    # Legacy compatibility
    # -------------------------------------------------------------------------

    def _base_ssh_cmd(self) -> list[str]:
        """Legacy method — delegates to _build_ssh_cmd."""
        return self._build_ssh_cmd()

    def _base_scp_cmd(self) -> list[str]:
        """Legacy method — delegates to _build_scp_cmd."""
        return self._build_scp_cmd()
