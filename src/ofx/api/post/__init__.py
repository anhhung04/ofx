"""Post-exploitation helper utilities."""

from __future__ import annotations

# Core abstractions
from .base import CommandRunner, PostRunnerBase

# Utilities
from .detect import detect_os
from .enum import linpeas_command, linux_exploit_suggester_command, winpeas_command
from .privilege import is_admin_from_whoami, is_root_from_id
from .registry import RunnerRegistry

# Runner implementations
from .runners import (
    PostSMBExec,
    PostSSH,
    PostWebShell,
    PostWinRM,
    PostWMIExec,
)
from .transfer import build_download_command

# Backward compatibility aliases
PostRunner = PostRunnerBase
PostRemote = PostWebShell


# Legacy function aliases for backward compatibility
def deploy_and_run(
    runner, local_path: str, remote_path: str, exec_cmd: str | None = None
) -> str:
    """Upload and execute a file on the remote target.

    DEPRECATED: Use runner.deploy_and_run() instead.
    """
    return runner.deploy_and_run(local_path, remote_path, exec_cmd)


def upload_via_webshell(client, local_path: str, remote_path: str) -> str:
    """DEPRECATED: Use PostWebShell(client).upload() instead."""
    from ofx.api.exploitation.webshell.client import WebShellClient

    return client.upload_file(local_path, remote_path)


def download_via_webshell(client, remote_path: str, local_path: str) -> None:
    """DEPRECATED: Use PostWebShell(client).download() instead."""
    return client.download_file(remote_path, local_path)


def upload_via_scp(
    local_path: str,
    remote_path: str,
    host: str,
    user: str | None = None,
    port: int = 22,
    identity_file: str | None = None,
    timeout: int | None = None,
) -> None:
    """DEPRECATED: Use PostSSH(...).upload() instead."""
    runner = PostSSH(host, user=user, port=port, identity_file=identity_file)
    runner.upload(local_path, remote_path, timeout=timeout)


def download_via_scp(
    remote_path: str,
    local_path: str,
    host: str,
    user: str | None = None,
    port: int = 22,
    identity_file: str | None = None,
    timeout: int | None = None,
) -> None:
    """DEPRECATED: Use PostSSH(...).download() instead."""
    runner = PostSSH(host, user=user, port=port, identity_file=identity_file)
    runner.download(remote_path, local_path, timeout=timeout)


def upload_via_winrm(post_winrm, local_path: str, remote_path: str) -> None:
    """DEPRECATED: Use PostWinRM(...).upload() instead."""
    post_winrm.upload(local_path, remote_path)


__all__ = [
    # Core
    "CommandRunner",
    "PostRunnerBase",
    "RunnerRegistry",
    # Runners
    "PostSSH",
    "PostWebShell",
    "PostWinRM",
    "PostSMBExec",
    "PostWMIExec",
    # Legacy aliases
    "PostRunner",
    "PostRemote",
    # Utilities
    "build_download_command",
    "detect_os",
    "is_admin_from_whoami",
    "is_root_from_id",
    "linpeas_command",
    "linux_exploit_suggester_command",
    "winpeas_command",
    # Legacy functions (deprecated)
    "deploy_and_run",
    "download_via_scp",
    "download_via_webshell",
    "upload_via_scp",
    "upload_via_webshell",
    "upload_via_winrm",
]
