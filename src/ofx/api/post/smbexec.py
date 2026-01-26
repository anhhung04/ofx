"""Minimal SMB exec helper for post-exploitation."""

from __future__ import annotations

from dataclasses import dataclass

from .remote import PostRunner

__all__ = ["PostSMBExec"]


@dataclass
class PostSMBExec(PostRunner):
    """Post-exploitation helper over SMB exec (Impacket).

    Requires the optional `impacket` package.
    """

    target: str
    username: str
    password: str
    domain: str = ""

    def __post_init__(self) -> None:
        try:
            from impacket.examples.secretsdump import RemoteOperations  # noqa: F401
            from impacket.examples.smbexec import SMBEXEC
            from impacket.smbconnection import SMBConnection
        except Exception as exc:  # pragma: no cover - import gate
            raise ImportError(
                "SMBExec support requires the 'impacket' package. "
                "Install it with: pip install impacket"
            ) from exc

        def _run(cmd: str) -> str:
            smb = SMBConnection(self.target, self.target)
            smb.login(self.username, self.password, self.domain)
            executor = SMBEXEC(self.username, self.password, self.domain, self.target, smb)
            output = executor.execute(cmd)
            smb.logoff()
            return output

        super().__init__(_run)
