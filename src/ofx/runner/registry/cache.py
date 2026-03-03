"""In-process caching wrapper for registry adapters."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any

from ofx.runner.registry.base import RegistryAdapter


class CachedRegistryAdapter(RegistryAdapter):
    """Add a small in-memory cache in front of any registry backend.

    The cache is per-process and TTL-based so remote backends (Redis, etcd,
    Memcached) avoid repeated network round-trips during hot loops. Writes
    invalidate cached entries to keep reads consistent within the process.
    """

    def __init__(
        self, backend: RegistryAdapter, ttl: float = 0.25, max_entries: int = 1024
    ) -> None:
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")

        self._backend = backend
        self._ttl = ttl
        self._max_entries = max_entries
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._cache_all: tuple[float, dict[str, Any]] | None = None
        self._lock = asyncio.Lock()

    def _is_fresh(self, ts: float) -> bool:
        return (time.monotonic() - ts) < self._ttl

    def _remember(self, key: str, value: Any) -> None:
        self._cache[key] = (time.monotonic(), value)
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)

    async def _set(self, key: str, value: Any) -> None:
        await self._backend.set(key, value)
        async with self._lock:
            self._remember(key, value)
            self._cache_all = None

    async def _get(self, key: str) -> Any | None:
        async with self._lock:
            cached = self._cache.get(key)
            if cached and self._is_fresh(cached[0]):
                return cached[1]

        value = await self._backend.get(key)
        async with self._lock:
            self._remember(key, value)
            self._cache_all = None
        return value

    async def _update(self, key: str, updates: dict[str, Any]) -> None:
        await self._backend.update(key, updates)
        async with self._lock:
            cached = self._cache.get(key)
            if cached and isinstance(cached[1], dict):
                merged = cached[1].copy()
                merged.update(updates)
                self._remember(key, merged)
            elif cached:
                self._remember(key, updates.copy())
            else:
                self._cache.pop(key, None)
            self._cache_all = None

    async def _delete(self, key: str) -> bool:
        deleted = await self._backend.delete(key)
        if deleted:
            async with self._lock:
                self._cache.pop(key, None)
                self._cache_all = None
        return deleted

    async def _exists(self, key: str) -> bool:
        value = await self._get(key)
        return value is not None

    async def _get_all(self) -> dict[str, Any]:
        async with self._lock:
            if self._cache_all and self._is_fresh(self._cache_all[0]):
                return self._cache_all[1]

        data = await self._backend.get_all()
        async with self._lock:
            for entry_key, entry_value in data.items():
                self._remember(entry_key, entry_value)
            self._cache_all = (time.monotonic(), data)
        return data

    async def _clear(self) -> None:
        await self._backend.clear()
        async with self._lock:
            self._cache.clear()
            self._cache_all = None

    async def _close(self) -> None:
        async with self._lock:
            self._cache.clear()
            self._cache_all = None
        await self._backend.close()
