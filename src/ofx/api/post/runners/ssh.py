"""SSH-based post-exploitation runner."""

from __future__ import annotations

import subprocess
from typing import Sequence

from ..base import PostRunnerBase
from ..registry import RunnerRegistry

__all__ = ["PostSSH"]


@RunnerRegistry.register("ssh")
class PostSSH(PostRunnerBase):
    """Post-exploitation runner over SSH.
    
    Uses native SSH/SCP commands for command execution and file transfers.
    
    Args:
        host: Target hostname or IP
        user: SSH username (optional)
        port: SSH port (default: 22)
        identity_file: Path to private key file
        connect_timeout: Connection timeout in seconds
        extra_args: Additional SSH arguments
        
    Example:
        >>> ssh = PostSSH("192.168.1.100", user="root", identity_file="~/.ssh/id_rsa")
        >>> ssh.run("whoami")
        'root'
        >>> ssh.upload("/tmp/exploit.sh", "/tmp/exploit.sh")
        >>> ssh.run("chmod +x /tmp/exploit.sh && /tmp/exploit.sh")
    """
    
    def __init__(
        self,
        host: str,
        user: str | None = None,
        port: int = 22,
        identity_file: str | None = None,
        connect_timeout: int = 10,
        extra_args: Sequence[str] | None = None,
    ):
        self.host = host
        self.user = user
        self.port = port
        self.identity_file = identity_file
        self.connect_timeout = connect_timeout
        self.extra_args = list(extra_args) if extra_args else []
    
    def _base_ssh_cmd(self) -> list[str]:
        """Build base SSH command with common options."""
        cmd = ["ssh", "-p", str(self.port), "-o", "StrictHostKeyChecking=no"]
        cmd.extend(["-o", f"ConnectTimeout={self.connect_timeout}"])
        if self.identity_file:
            cmd.extend(["-i", self.identity_file])
        if self.extra_args:
            cmd.extend(self.extra_args)
        target = f"{self.user}@{self.host}" if self.user else self.host
        cmd.append(target)
        return cmd
    
    def _base_scp_cmd(self) -> list[str]:
        """Build base SCP command with common options."""
        cmd = ["scp", "-P", str(self.port), "-o", "StrictHostKeyChecking=no"]
        if self.identity_file:
            cmd.extend(["-i", self.identity_file])
        if self.extra_args:
            cmd.extend(self.extra_args)
        return cmd
    
    def _target_path(self, path: str) -> str:
        """Format path with user@host prefix for SCP."""
        if self.user:
            return f"{self.user}@{self.host}:{path}"
        return f"{self.host}:{path}"
    
    def run(self, command: str, timeout: int | None = None) -> str:
        """Execute a command over SSH.
        
        Args:
            command: Shell command to execute
            timeout: Command timeout in seconds
            
        Returns:
            Command output
            
        Raises:
            RuntimeError: If SSH command fails
        """
        cmd = self._base_ssh_cmd() + [command]
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"SSH failed: {result.returncode}")
        return result.stdout
    
    def upload(self, local_path: str, remote_path: str, timeout: int | None = None) -> None:
        """Upload a file via SCP.
        
        Args:
            local_path: Local file path
            remote_path: Remote destination path
            timeout: Transfer timeout in seconds
        """
        cmd = self._base_scp_cmd() + [local_path, self._target_path(remote_path)]
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"SCP upload failed: {result.returncode}")
    
    def download(self, remote_path: str, local_path: str, timeout: int | None = None) -> None:
        """Download a file via SCP.
        
        Args:
            remote_path: Remote file path
            local_path: Local destination path
            timeout: Transfer timeout in seconds
        """
        cmd = self._base_scp_cmd() + [self._target_path(remote_path), local_path]
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"SCP download failed: {result.returncode}")
