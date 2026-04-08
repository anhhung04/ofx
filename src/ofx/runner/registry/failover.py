"""Failover registry adapter that falls back to memory on backend errors."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ofx.runner.registry.base import RegistryAdapter
from ofx.runner.registry.memory import MemoryJobRegistry
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

# Wait at least this many seconds before retrying the primary backend.
_RECONNECT_INTERVAL = 30.0


class FailoverRegistryAdapter(RegistryAdapter):
    """Wrap a primary registry and fail over to in-memory on errors.

    The adapter switches to the fallback after the first backend failure
    and periodically retries the primary backend so that transient network
    issues don't permanently degrade to in-memory storage.
    ``asyncio.CancelledError`` is always propagated to avoid hiding cancels.
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
        self._last_primary_attempt: float = 0.0

    async def _call(self, method_name: str, *args, **kwargs):
        async with self._lock:
            # Periodically retry primary when in fallback mode
            if (
                self._use_fallback
                and (time.monotonic() - self._last_primary_attempt) >= _RECONNECT_INTERVAL
            ):
                self._last_primary_attempt = time.monotonic()
                try:
                    method = getattr(self._primary, method_name)
                    result = await method(*args, **kwargs)
                    # Primary recovered — switch back
                    logger.info("Registry primary backend recovered, switching back")
                    self._use_fallback = False
                    return result
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.debug("Primary registry still unavailable: %s", exc)

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
                self._last_primary_attempt = time.monotonic()
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
        await self._fallback.clear()

    async def _close(self) -> None:
        try:
            await self._primary.close()
        except Exception as e:
            logger.debug("Failed to close primary registry: %s", e)
        await self._fallback.close()
