"""Start an SSH dynamic SOCKS5 tunnel to the configured jump host."""

from __future__ import annotations

import socket
import subprocess
import time

_TUNNEL_TIMEOUT_SECONDS = 15.0
_POLL_INTERVAL_SECONDS = 0.5


def _wait_for_local_port(proc: subprocess.Popen, port: int) -> None:
    """Wait until the tunnel listens on *port* or ssh exits."""
    deadline = time.monotonic() + _TUNNEL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            detail = ""
            if proc.stderr is not None:
                detail = proc.stderr.read().strip()
            raise RuntimeError(
                f"ssh exited before the tunnel was ready (rc={proc.returncode}): {detail}"
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(_POLL_INTERVAL_SECONDS)
    raise RuntimeError(
        f"SSH tunnel did not open local port {port} within "
        f"{int(_TUNNEL_TIMEOUT_SECONDS)}s"
    )


def run(ctx):
    ssh_host = str(ctx.inputs.get("ssh_host", "")).strip()
    if not ssh_host:
        raise ValueError("ssh_host is required for ssh-tunnel mode")

    ssh_port = str(ctx.inputs.get("ssh_port", "22")).strip() or "22"
    ssh_user = str(ctx.inputs.get("ssh_user", "root")).strip() or "root"
    local_port = int(str(ctx.inputs.get("local_port", "1080")).strip() or "1080")

    cmd = [
        "ssh",
        "-N",
        "-D",
        str(local_port),
        "-p",
        ssh_port,
        "-o",
        "BatchMode=yes",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ServerAliveInterval=60",
        f"{ssh_user}@{ssh_host}",
    ]
    print(f"[*] Establishing SSH dynamic tunnel to {ssh_user}@{ssh_host}:{ssh_port}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        _wait_for_local_port(proc, local_port)
    except Exception:
        proc.terminate()
        raise

    ctx.add_outputs(tunnel_pid=str(proc.pid), local_port=str(local_port))
    print(f"[+] SSH tunnel active: SOCKS5 on localhost:{local_port} (PID {proc.pid})")
