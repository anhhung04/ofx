"""Minimal WinRM runner for post-exploitation helpers."""

from __future__ import annotations

from dataclasses import dataclass

from .remote import PostRunner

__all__ = ["PostWinRM"]


@dataclass
class PostWinRM(PostRunner):
    """Post-exploitation helper over WinRM.

    Requires the optional `pywinrm` package.
    """

    host: str
    username: str
    password: str
    transport: str = "ntlm"
    server_cert_validation: str = "ignore"

    def __post_init__(self) -> None:
        try:
            import winrm  # type: ignore
        except Exception as exc:  # pragma: no cover - import gate
            raise ImportError(
                "WinRM support requires the 'pywinrm' package. "
                "Install it with: pip install pywinrm"
            ) from exc

        endpoint = f"http://{self.host}:5985/wsman"
        session = winrm.Session(
            endpoint,
            auth=(self.username, self.password),
            transport=self.transport,
            server_cert_validation=self.server_cert_validation,
        )

        def _run(cmd: str) -> str:
            result = session.run_cmd(cmd)
            if result.status_code != 0:
                err = result.std_err.decode(errors="ignore").strip()
                raise RuntimeError(err or f"WinRM failed: {result.status_code}")
            return result.std_out.decode(errors="ignore")

        super().__init__(_run)
