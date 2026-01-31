"""WinRM-based post-exploitation runner."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..base import PostRunnerBase
from ..registry import RunnerRegistry

__all__ = ["PostWinRM"]


@RunnerRegistry.register("winrm")
@dataclass
class PostWinRM(PostRunnerBase):
    """Post-exploitation runner over WinRM.
    
    Requires the optional `pywinrm` package.
    
    Args:
        host: Target hostname or IP
        username: Windows username
        password: Windows password
        transport: WinRM transport (default: "ntlm")
        server_cert_validation: Certificate validation mode (default: "ignore")
        
    Example:
        >>> winrm = PostWinRM("192.168.1.100", "Administrator", "P@ssw0rd!")
        >>> winrm.run("whoami")
        'corp\\administrator'
    """
    
    host: str
    username: str
    password: str
    transport: str = "ntlm"
    server_cert_validation: str = "ignore"
    _session: Any = field(default=None, init=False, repr=False)
    
    def __post_init__(self) -> None:
        try:
            import winrm  # type: ignore
        except Exception as exc:  # pragma: no cover - import gate
            raise ImportError(
                "WinRM support requires the 'pywinrm' package. "
                "Install it with: pip install pywinrm"
            ) from exc
        
        endpoint = f"http://{self.host}:5985/wsman"
        self._session = winrm.Session(
            endpoint,
            auth=(self.username, self.password),
            transport=self.transport,
            server_cert_validation=self.server_cert_validation,
        )
    
    def run(self, command: str) -> str:
        """Execute a command via WinRM.
        
        Args:
            command: Windows command to execute
            
        Returns:
            Command output
            
        Raises:
            RuntimeError: If command fails
        """
        result = self._session.run_cmd(command)
        if result.status_code != 0:
            err = result.std_err.decode(errors="ignore").strip()
            raise RuntimeError(err or f"WinRM failed: {result.status_code}")
        return result.std_out.decode(errors="ignore")
    
    def run_ps(self, script: str) -> str:
        """Execute a PowerShell script via WinRM.
        
        Args:
            script: PowerShell script to execute
            
        Returns:
            Script output
            
        Raises:
            RuntimeError: If script fails
        """
        result = self._session.run_ps(script)
        if result.status_code != 0:
            err = result.std_err.decode(errors="ignore").strip()
            raise RuntimeError(err or f"PowerShell failed: {result.status_code}")
        return result.std_out.decode(errors="ignore")
    
    def upload(self, local_path: str, remote_path: str) -> None:
        """Upload a file via WinRM using base64 encoding.
        
        Args:
            local_path: Local file path
            remote_path: Remote destination path (Windows path)
        """
        data = Path(local_path).read_bytes()
        encoded = base64.b64encode(data).decode("ascii")
        
        # Use PowerShell to decode and write the file
        script = (
            f"$b = [Convert]::FromBase64String('{encoded}'); "
            f"[IO.File]::WriteAllBytes('{remote_path}', $b)"
        )
        self.run_ps(script)
    
    def download(self, remote_path: str, local_path: str) -> None:
        """Download a file via WinRM using base64 encoding.
        
        Args:
            remote_path: Remote file path (Windows path)
            local_path: Local destination path
        """
        # Read and encode file on remote
        script = f"[Convert]::ToBase64String([IO.File]::ReadAllBytes('{remote_path}'))"
        encoded = self.run_ps(script).strip()
        
        # Decode and write locally
        data = base64.b64decode(encoded)
        Path(local_path).write_bytes(data)
