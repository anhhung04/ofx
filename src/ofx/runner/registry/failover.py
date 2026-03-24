"""Failover registry adapter that falls back to memory on backend errors."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ofx.runner.registry.base import RegistryAdapter
from ofx.runner.registry.memory import MemoryJobRegistry
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class FailoverRegistryAdapter(RegistryAdapter):
    """Wrap a primary registry and fail over to in-memory on errors.

    The adapter switches permanently to the fallback after the first backend
    failure. ``asyncio.CancelledError`` is propagated to avoid hiding cancels.
    """

    def __init__(
        self,
        primary: RegistryAdapter,
        fallback: RegistryAdapter | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback or MemoryJobRegistry()
        self._use_fallback = False
        self._lock = asyncio.Lock()

    async def _call(self, method_name: str, *args, **kwargs):
        async with self._lock:
            target = self._fallback if self._use_fallback else self._primary
        method = getattr(target, method_name)
        try:
            return await method(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._use_fallback:
                raise
            logger.warning(
                "Registry backend error (%s), switching to in-memory fallback: %s",
                type(exc).__name__,
                exc,
            )
            async with self._lock:
                self._use_fallback = True
            method = getattr(self._fallback, method_name)
            return await method(*args, **kwargs)

    async def _set(self, key: str, value: Any) -> None:
        await self._call("set", key, value)

    async def _get(self, key: str) -> Any | None:
        return await self._call("get", key)

    async def _update(self, key: str, updates: dict[str, Any]) -> None:
        await self._call("update", key, updates)

    async def _delete(self, key: str) -> bool:
        return await self._call("delete", key)

    async def _exists(self, key: str) -> bool:
        return await self._call("exists", key)

    async def _get_all(self) -> dict[str, Any]:
        return await self._call("get_all")

    async def _clear(self) -> None:
        # Clear both for safety
        try:
            await self._primary.clear()
        except Exception as e:
            logger.debug("Failed to clear primary registry: %s", e)
            pass
        await self._fallback.clear()

    async def _close(self) -> None:
        try:
            await self._primary.close()
        except Exception as e:
            logger.debug("Failed to close primary registry: %s", e)
            pass
        await self._fallback.close()
