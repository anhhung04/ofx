"""Minimal WMI exec helper for post-exploitation."""

from __future__ import annotations

from dataclasses import dataclass

from .remote import PostRunner

__all__ = ["PostWMIExec"]


@dataclass
class PostWMIExec(PostRunner):
    """Post-exploitation helper over WMI exec (Impacket).

    Requires the optional `impacket` package.
    """

    target: str
    username: str
    password: str
    domain: str = ""

    def __post_init__(self) -> None:
        try:
            from impacket.examples.wmiexec import WMIEXEC
        except Exception as exc:  # pragma: no cover - import gate
            raise ImportError(
                "WMIExec support requires the 'impacket' package. "
                "Install it with: pip install impacket"
            ) from exc

        def _run(cmd: str) -> str:
            executor = WMIEXEC(cmd, self.username, self.password, self.domain, self.target)
            return executor.run()  # returns command output

        super().__init__(_run)
