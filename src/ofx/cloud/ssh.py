"""SSH and WinRM connectivity helpers for cloud instances."""

from __future__ import annotations

import time
import asyncio
import logging
from ofx.models.cloud import CloudConfig

logger = logging.getLogger("ofx")


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
    deadline = asyncio.get_event_loop().time() + timeout
    attempts = 0

    while asyncio.get_event_loop().time() < deadline:
        attempts += 1
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=10
            )
            writer.close()
            await writer.wait_closed()
            logger.debug(f"SSH reachable on {host}:{port} after {attempts} attempts")
            return True
        except (TimeoutError, OSError):
            pass
        await asyncio.sleep(interval)

    raise TimeoutError(f"SSH on {host}:{port} not reachable after {timeout}s")


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
    deadline = asyncio.get_event_loop().time() + timeout
    attempts = 0

    while asyncio.get_event_loop().time() < deadline:
        attempts += 1
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=10
            )
            writer.close()
            await writer.wait_closed()
            logger.debug(f"WinRM reachable on {host}:{port} after {attempts} attempts")
            return True
        except (TimeoutError, OSError):
            pass
        await asyncio.sleep(interval)

    raise TimeoutError(f"WinRM on {host}:{port} not reachable after {timeout}s")


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
    if os_type == "windows":
        return await wait_for_winrm(host, winrm_port, timeout)
    else:
        return await wait_for_ssh(host, ssh_port, timeout)

async def wait_for_login(
    host: str,
    cfg: CloudConfig,
    timeout: int = 300,
) -> bool:
    """
    Verified login availability by attempting a real connection 
    using the provided credentials and transport settings.
    """
    from ofx.api.post.runners.ssh import PostSSH
    from ofx.api.post.runners.winrm import PostWinRM

    start_time = time.time()
    is_windows = cfg.connection_type == "winrm" or getattr(cfg, "os_type", "") == "windows"
    
    ssh_port = cfg.ssh_port or 22
    winrm_port = cfg.winrm_port or (5986 if cfg.winrm_ssl else 5985)

    def _try_ssh():
        r = PostSSH(
            host=host,
            port=ssh_port,
            user=cfg.ssh_user,
            identity_file=cfg.ssh_key,
            password=cfg.ssh_password,
            connect_timeout=10,
        )
        r.run("id")

    def _try_winrm():
        r = PostWinRM(
            host=host,
            port=winrm_port,
            username=cfg.winrm_user,
            password=cfg.winrm_password,
            ssl=cfg.winrm_ssl,
            transport=cfg.winrm_transport,
            command_timeout=10,
        )
        r.run("whoami")

    probe = _try_winrm if is_windows else _try_ssh

    while time.time() - start_time < timeout:
        try:
            await asyncio.to_thread(probe)
            return True
        except Exception:
            await asyncio.sleep(5)

    return False