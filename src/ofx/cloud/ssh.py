"""SSH and WinRM connectivity helpers for cloud instances."""

from __future__ import annotations

import asyncio
import logging

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
        except (OSError, asyncio.TimeoutError):
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
        except (OSError, asyncio.TimeoutError):
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
