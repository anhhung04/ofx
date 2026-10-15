"""Async TCP connect port scanner."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass

__all__ = [
    "TOP_100_PORTS",
    "PortResult",
    "async_port_scan",
    "port_scan",
]

TOP_100_PORTS: list[int] = [
    20,
    21,
    22,
    23,
    25,
    53,
    69,
    79,
    80,
    81,
    88,
    110,
    111,
    135,
    139,
    143,
    389,
    443,
    445,
    636,
    902,
    993,
    995,
    1080,
    1194,
    1433,
    1521,
    1723,
    1883,
    2049,
    2121,
    2375,
    2376,
    3000,
    3306,
    3389,
    4000,
    4443,
    4848,
    5000,
    5432,
    5601,
    5672,
    5900,
    6379,
    6443,
    7001,
    7070,
    7443,
    7474,
    8000,
    8001,
    8008,
    8009,
    8080,
    8081,
    8082,
    8161,
    8443,
    8500,
    8888,
    8983,
    9000,
    9042,
    9090,
    9092,
    9200,
    9300,
    9418,
    9999,
    10250,
    11211,
    27017,
    28017,
    50000,
    50070,
    61616,
]

@dataclass
class PortResult:
    host: str
    port: int
    open: bool
    banner: str = ""

async def _probe(host: str, port: int, timeout: float) -> PortResult:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        banner = ""
        with suppress(OSError, TimeoutError):
            data = await asyncio.wait_for(reader.read(256), timeout=1.0)
            banner = data.decode(errors="ignore").strip()
        writer.close()
        with suppress(OSError):
            await writer.wait_closed()
        return PortResult(host=host, port=port, open=True, banner=banner)
    except (OSError, TimeoutError):
        return PortResult(host=host, port=port, open=False)

async def async_port_scan(
    host: str,
    ports: list[int] | None = None,
    *,
    concurrency: int = 250,
    timeout: float = 1.5,
) -> list[PortResult]:
    """Async TCP connect scan. Returns only open :class:`PortResult` entries.

    Args:
        host: Target hostname or IP address.
        ports: Ports to probe. Defaults to :data:`TOP_100_PORTS`.
        concurrency: Maximum simultaneous connection attempts.
        timeout: Per-connection timeout in seconds.
    """
    if ports is None:
        ports = TOP_100_PORTS
    sem = asyncio.Semaphore(concurrency)

    async def _guarded(port: int) -> PortResult:
        async with sem:
            return await _probe(host, port, timeout)

    results = await asyncio.gather(*[_guarded(p) for p in ports])
    return sorted([r for r in results if r.open], key=lambda r: r.port)

def port_scan(
    host: str,
    ports: list[int] | None = None,
    *,
    concurrency: int = 250,
    timeout: float = 1.5,
) -> list[PortResult]:
    """Synchronous wrapper around :func:`async_port_scan`."""
    return asyncio.run(
        async_port_scan(host, ports, concurrency=concurrency, timeout=timeout)
    )
