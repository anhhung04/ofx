"""Abstract base classes and protocols for post-exploitation runners."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .detect import detect_os
from .privilege import is_admin_from_whoami, is_root_from_id
from .transfer import build_download_command

if TYPE_CHECKING:
    pass

__all__ = ["CommandRunner", "PostRunnerBase"]


@runtime_checkable
class CommandRunner(Protocol):
    """Protocol for command execution compatibility.

    Use this for duck-typing checks when you only need command execution.

    Example:
        >>> def run_enumeration(runner: CommandRunner):
        ...     return runner.run("id")
    """

    def run(self, command: str, timeout: int | None = None) -> str:
        """Execute a command and return output."""
        ...


class PostRunnerBase(ABC):
    """Abstract base class for all post-exploitation runners.

    Provides a consistent interface for:
    - Command execution
    - File transfers (upload/download)
    - Interactive shell sessions
    - OS detection and privilege checking

    Subclasses must implement:
    - run(command: str) -> str

    And optionally override:
    - upload(local_path, remote_path)
    - download(remote_path, local_path)
    - interactive_shell(**kwargs)

    Example:
        >>> class MyRunner(PostRunnerBase):
        ...     def run(self, command: str) -> str:
        ...         return execute_somehow(command)
        ...
        >>> runner = MyRunner()
        >>> runner.detect_os()
        'linux'
    """

    @abstractmethod
    def run(self, command: str, timeout: int | None = None) -> str:
        """Execute a command on the remote target.

        Args:
            command: Shell command to execute
            timeout: Optional timeout in seconds for command execution

        Returns:
            Command output as string
        """
        ...

    # -------------------------------------------------------------------------
    # File Transfer Methods (override in subclass if supported)
    # -------------------------------------------------------------------------

    def upload(self, local_path: str, remote_path: str) -> None:
        """Upload a file to the remote target.

        Args:
            local_path: Local file path to upload
            remote_path: Destination path on target

        Raises:
            NotImplementedError: If subclass doesn't support uploads
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support file upload"
        )

    def download(self, remote_path: str, local_path: str) -> None:
        """Download a file from the remote target.

        Args:
            remote_path: File path on target
            local_path: Local destination path

        Raises:
            NotImplementedError: If subclass doesn't support downloads
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support file download"
        )

    # -------------------------------------------------------------------------
    # Interactive Shell (override in subclass if supported)
    # -------------------------------------------------------------------------

    def supports_interactive(self) -> bool:
        """Check if interactive shell is supported.

        Returns:
            True if interactive_shell() is available
        """
        return False

    def interactive_shell(self, **kwargs) -> None:
        """Start an interactive shell session.

        Raises:
            NotImplementedError: If subclass doesn't support interactive shells
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support interactive shell"
        )

    # -------------------------------------------------------------------------
    # Common Utility Methods
    # -------------------------------------------------------------------------

    def get_uname(self) -> str:
        """Fetch uname output (Unix-like systems)."""
        return self.run("uname -a")

    def get_id(self) -> str:
        """Fetch id output (Unix-like systems)."""
        return self.run("id")

    def detect_os(self) -> str:
        """Detect OS family from remote uname output.

        Returns:
            One of: "linux", "darwin", "windows", "unknown"
        """
        return detect_os(self.get_uname())

    def is_root(self) -> bool:
        """Check for root privileges via remote id output."""
        return is_root_from_id(self.get_id())

    def is_admin(self) -> bool:
        """Check for admin privileges via remote whoami output (Windows)."""
        return is_admin_from_whoami(self.run("whoami"))

    def download_command(self, url: str, dest: str, platform: str | None = None) -> str:
        """Build a download command for the remote platform.

        Args:
            url: Remote URL to download
            dest: Destination path on target
            platform: "windows" or "unix", auto-detected if None

        Returns:
            Shell command string for downloading
        """
        if platform is None:
            platform = "windows" if self.detect_os() == "windows" else "unix"
        return build_download_command(url, dest, platform=platform)

    # -------------------------------------------------------------------------
    # Deploy and Run Helper
    # -------------------------------------------------------------------------

    def deploy_and_run(
        self,
        local_path: str,
        remote_path: str,
        exec_cmd: str | None = None,
    ) -> str:
        """Upload a local file and execute it on the remote target.

        Args:
            local_path: Local file to upload
            remote_path: Destination on target
            exec_cmd: Command to run (defaults to remote_path)

        Returns:
            Execution output
        """
        self.upload(local_path, remote_path)
        return self.run(exec_cmd or remote_path)

    def cleanup(self) -> None:
        """Optional cleanup after deploy_and_run. Default does nothing."""
        # No-op by default; subclasses can override if needed
        return None
