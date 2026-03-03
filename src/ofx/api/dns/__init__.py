"""Lightweight DNS helpers for recon and callback prep."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Iterable
from random import uniform

__all__ = [
    "resolve_host",
    "resolve_host_sync",
    "bruteforce_subdomains",
    "bruteforce_subdomains_sync",
]


async def resolve_host(host: str, *, timeout: float = 2.0) -> list[str]:
    """Resolve a hostname to all available IPs."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    results: list[str] = []
    for family, _, _, _, sockaddr in infos:
        ip = sockaddr[0]
        if family == socket.AF_INET6:
            results.append(ip.split("%", 1)[0])
        else:
            results.append(ip)
    return sorted(set(results))


def resolve_host_sync(host: str, *, timeout: float = 2.0) -> list[str]:
    """Synchronous resolver wrapper."""
    socket.setdefaulttimeout(timeout)
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    results: list[str] = []
    for family, _, _, _, sockaddr in infos:
        ip = sockaddr[0]
        if family == socket.AF_INET6:
            results.append(ip.split("%", 1)[0])
        else:
            results.append(ip)
    return sorted(set(results))


async def bruteforce_subdomains(
    domain: str,
    candidates: Iterable[str],
    *,
    concurrency: int = 100,
    timeout: float = 2.0,
    jitter: float = 0.0,
) -> list[tuple[str, str]]:
    """Concurrent subdomain brute-force using system DNS."""

    async def _resolve(name: str) -> tuple[str, str] | None:
        target = f"{name}.{domain}" if name else domain
        try:
            await asyncio.sleep(uniform(0, jitter))
            ips = await resolve_host(target, timeout=timeout)
            return target, ips[0]
        except Exception:
            return None

    sem = asyncio.Semaphore(max(1, concurrency))
    results: list[tuple[str, str]] = []

    async def _worker(name: str):
        async with sem:
            hit = await _resolve(name)
            if hit:
                results.append(hit)

    tasks = [asyncio.create_task(_worker(name.strip())) for name in candidates if name]
    if tasks:
        await asyncio.gather(*tasks)
    return sorted(results)


def bruteforce_subdomains_sync(
    domain: str,
    candidates: Iterable[str],
    *,
    concurrency: int = 100,
    timeout: float = 2.0,
    jitter: float = 0.0,
) -> list[tuple[str, str]]:
    """Sync wrapper for subdomain brute-force."""
    return asyncio.run(
        bruteforce_subdomains(
            domain,
            candidates,
            concurrency=concurrency,
            timeout=timeout,
            jitter=jitter,
        )
    )
