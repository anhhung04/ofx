"""Remote post-exploitation helpers over webshells or SSH."""

from __future__ import annotations

import subprocess
from typing import Callable, Sequence

from ofx.api.exploitation.webshell.client import WebShellClient

from .detect import detect_os
from .privilege import is_admin_from_whoami, is_root_from_id
from .transfer import build_download_command

__all__ = ["PostRunner", "PostRemote", "PostSSH", "PostWebShell"]


class PostRunner:
    """Generic post-exploitation helper for any command runner."""

    def __init__(
        self,
        run_fn: Callable[[str], str],
        interactive_fn: Callable[..., None] | None = None,
    ):
        self._run_fn = run_fn
        self._interactive_fn = interactive_fn

    def run(self, command: str) -> str:
        """Run a shell command via the configured runner."""
        return self._run_fn(command)

    def get_uname(self) -> str:
        """Fetch uname output (Unix-like)."""
        return self.run("uname -a")

    def get_id(self) -> str:
        """Fetch id output (Unix-like)."""
        return self.run("id")

    def detect_os(self) -> str:
        """Detect OS from remote uname output."""
        return detect_os(self.get_uname())

    def is_root(self) -> bool:
        """Check for root via remote id output."""
        return is_root_from_id(self.get_id())

    def is_admin(self) -> bool:
        """Check for admin via remote whoami output (Windows)."""
        return is_admin_from_whoami(self.run("whoami"))

    def download_command(self, url: str, dest: str, platform: str | None = None) -> str:
        """Build a download command for the remote platform.

        If platform is None, uses detect_os() to infer unix/windows.
        """
        if platform is None:
            platform = "windows" if self.detect_os() == "windows" else "unix"
        return build_download_command(url, dest, platform=platform)

    def interactive_shell(self, **kwargs) -> None:
        """Start an interactive shell session if supported."""
        if self._interactive_fn is None:
            raise RuntimeError("interactive_shell is not supported for this runner")
        return self._interactive_fn(**kwargs)


class PostWebShell(PostRunner):
    """Post-exploitation helper bound to a WebShellClient."""

    def __init__(self, client: WebShellClient):
        self.client = client
        super().__init__(client.run_command, client.interactive_shell)


PostRemote = PostWebShell


class PostSSH(PostRunner):
    """Remote post-exploitation helper over SSH."""

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
        super().__init__(self._run_ssh)

    def _base_cmd(self) -> list[str]:
        cmd = ["ssh", "-p", str(self.port), "-o", "StrictHostKeyChecking=no"]
        cmd.extend(["-o", f"ConnectTimeout={self.connect_timeout}"])
        if self.identity_file:
            cmd.extend(["-i", self.identity_file])
        if self.extra_args:
            cmd.extend(self.extra_args)
        target = f"{self.user}@{self.host}" if self.user else self.host
        cmd.append(target)
        return cmd

    def _run_ssh(self, command: str, timeout: int | None = None) -> str:
        cmd = self._base_cmd() + [command]
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
