"""SSH and WinRM connectivity helpers for cloud instances."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from ofx.models.cloud import CloudConfig

logger = logging.getLogger("ofx")

_LOGIN_RETRY_INTERVAL = 5

async def _wait_for_port(
    host: str,
    port: int,
    *,
    label: str,
    timeout: int,
    interval: int,
) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    attempts = 0

    while asyncio.get_running_loop().time() < deadline:
        attempts += 1
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=10
            )
            writer.close()
            await writer.wait_closed()
            logger.debug("%s reachable on %s:%s after %s attempts", label, host, port, attempts)
            return True
        except (TimeoutError, OSError):
            await asyncio.sleep(interval)

    raise TimeoutError(f"{label} on {host}:{port} not reachable after {timeout}s")

async def wait_for_ssh(
    host: str, port: int = 22, timeout: int = 300, interval: int = 5
) -> bool:
    """Wait until SSH port is reachable on a host.

    Args:
        host: Target hostname or IP.
        port: SSH port (default 22).
        timeout: Max seconds to wait.
        interval: Seconds between checks.

    Returns:
        True if SSH became reachable within timeout.

    Raises:
        TimeoutError: If SSH not reachable within timeout.
    """
    return await _wait_for_port(
        host,
        port,
        label="SSH",
        timeout=timeout,
        interval=interval,
    )

async def wait_for_winrm(
    host: str, port: int = 5985, timeout: int = 300, interval: int = 10
) -> bool:
    """Wait until WinRM port is reachable on a host.

    Args:
        host: Target hostname or IP.
        port: WinRM port (default 5985, or 5986 for HTTPS).
        timeout: Max seconds to wait.
        interval: Seconds between checks.

    Returns:
        True if WinRM became reachable within timeout.

    Raises:
        TimeoutError: If WinRM not reachable within timeout.
    """
    return await _wait_for_port(
        host,
        port,
        label="WinRM",
        timeout=timeout,
        interval=interval,
    )

async def wait_for_connectivity(
    host: str,
    os_type: str = "linux",
    ssh_port: int = 22,
    winrm_port: int = 5985,
    timeout: int = 300,
) -> bool:
    """Wait for instance connectivity based on OS type.

    Args:
        host: Target hostname or IP.
        os_type: "linux" or "windows".
        ssh_port: SSH port for Linux.
        winrm_port: WinRM port for Windows.
        timeout: Max seconds to wait.

    Returns:
        True if became reachable.
    """
    if str(os_type).lower() == "windows":
        return await wait_for_winrm(host, winrm_port, timeout)
    return await wait_for_ssh(host, ssh_port, timeout)

def _probe_ssh_login(host: str, cfg: CloudConfig) -> None:
    from ofx.api.post.runners.ssh import PostSSH

    runner = PostSSH(
        host=host,
        port=cfg.ssh_port or 22,
        user=cfg.ssh_user,
        identity_file=cfg.ssh_key,
        password=cfg.ssh_password,
        connect_timeout=10,
    )
    runner.run("id")

def _probe_winrm_login(host: str, cfg: CloudConfig) -> None:
    from ofx.api.post.runners.winrm import PostWinRM

    runner = PostWinRM(
        host=host,
        port=cfg.winrm_port or (5986 if cfg.winrm_ssl else 5985),
        username=cfg.winrm_user,
        password=cfg.winrm_password,
        ssl=cfg.winrm_ssl,
        transport=cfg.winrm_transport,
        command_timeout=10,
    )
    runner.run("whoami")

async def wait_for_login(
    host: str,
    cfg: CloudConfig,
    timeout: int = 300,
) -> bool:
    """Verify login availability by attempting a real authenticated connection.

    Raises:
        TimeoutError: If the host does not accept login within ``timeout`` seconds.
    """
    start_time = time.time()
    if cfg.connection_type == "winrm" or getattr(cfg, "os_type", "") == "windows":
        probe: Callable[[], None] = lambda: _probe_winrm_login(host, cfg)
    else:
        probe = lambda: _probe_ssh_login(host, cfg)
    last_error: Exception | None = None

    while time.time() - start_time < timeout:
        try:
            await asyncio.to_thread(probe)
            return True
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(_LOGIN_RETRY_INTERVAL)

    raise TimeoutError(
        f"Login to {host} not established after {timeout}s"
        + (f": {last_error}" if last_error else "")
    )
