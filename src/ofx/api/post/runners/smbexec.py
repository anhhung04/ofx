"""SMBExec-based post-exploitation runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..base import PostRunnerBase
from ..registry import RunnerRegistry

__all__ = ["PostSMBExec"]


@RunnerRegistry.register("smbexec")
@dataclass
class PostSMBExec(PostRunnerBase):
    """Post-exploitation runner over SMB exec (Impacket).

    Requires the optional `impacket` package.

    Args:
        target: Target hostname or IP
        username: Windows username
        password: Windows password
        domain: Windows domain (optional)

    Example:
        >>> smb = PostSMBExec("192.168.1.100", "admin", "P@ssw0rd!", domain="CORP")
        >>> smb.run("whoami")
        'corp\\admin'
    """

    target: str
    username: str
    password: str
    domain: str = ""
    _smb_module: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            from impacket.examples import smbexec as smbexec_module
            from impacket.examples.secretsdump import RemoteOperations  # noqa: F401
            from impacket.smbconnection import SMBConnection  # noqa: F401

            self._smb_module = smbexec_module
        except Exception as exc:  # pragma: no cover - import gate
            raise ImportError(
                "SMBExec support requires the 'impacket' package. "
                "Install it with: pip install impacket"
            ) from exc

    def run(self, command: str, timeout: int | None = None) -> str:  # noqa: ARG002
        """Execute a command via SMB exec.

        Args:
            command: Windows command to execute

        Returns:
            Command output
        """
        from impacket.smbconnection import SMBConnection

        smb = SMBConnection(self.target, self.target)
        try:
            smb.login(self.username, self.password, self.domain)
            executor = self._smb_module.SMBEXEC(
                self.username, self.password, self.domain, self.target, smb
            )
            return executor.execute(command)
        finally:
            try:
                smb.logoff()
            except Exception:
                pass

    def upload(self, local_path: str, remote_path: str) -> None:
        """Upload a file via SMB.

        Args:
            local_path: Local file path
            remote_path: Remote destination path (UNC format: share/path)
        """
        from impacket.smbconnection import SMBConnection

        smb = SMBConnection(self.target, self.target)
        try:
            smb.login(self.username, self.password, self.domain)

            # Parse share and path from remote_path
            # Expected format: "SHARE/path/to/file" or "C$/path/to/file"
            parts = remote_path.replace("\\", "/").split("/", 1)
            share = parts[0]
            path = parts[1] if len(parts) > 1 else ""

            with open(local_path, "rb") as f:
                smb.putFile(share, path, f.read)
        finally:
            try:
                smb.logoff()
            except Exception:
                pass

    def download(self, remote_path: str, local_path: str) -> None:
        """Download a file via SMB.

        Args:
            remote_path: Remote file path (UNC format: share/path)
            local_path: Local destination path
        """
        from impacket.smbconnection import SMBConnection

        smb = SMBConnection(self.target, self.target)
        try:
            smb.login(self.username, self.password, self.domain)

            # Parse share and path
            parts = remote_path.replace("\\", "/").split("/", 1)
            share = parts[0]
            path = parts[1] if len(parts) > 1 else ""

            with open(local_path, "wb") as f:
                smb.getFile(share, path, f.write)
        finally:
            try:
                smb.logoff()
            except Exception:
                pass
