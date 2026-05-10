"""Failover registry adapter with circuit breaker and exponential backoff."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ofx.runner.registry.base import RegistryAdapter
from ofx.runner.registry.memory import MemoryJobRegistry
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

# Backoff configuration
_INITIAL_BACKOFF = 5.0       # seconds before first retry
_MAX_BACKOFF = 300.0         # 5 minutes max between retries
_BACKOFF_FACTOR = 2.0        # double each failure
_CIRCUIT_BREAK_AFTER = 5     # open circuit after N consecutive failures


class FailoverRegistryAdapter(RegistryAdapter):
    """Wrap a primary registry and fail over to in-memory on errors.

    Features:
    - Exponential backoff on primary retry (5s → 10s → 20s → ... → 300s)
    - Circuit breaker: stops retrying after N consecutive failures
    - Clear warning when falling back to volatile in-memory storage
    - ``asyncio.CancelledError`` is always propagated
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
        self._consecutive_failures: int = 0
        self._current_backoff: float = _INITIAL_BACKOFF
        self._circuit_open: bool = False

    @property
    def health(self) -> dict[str, Any]:
        """Return current failover state for debugging/observability."""
        return {
            "using_fallback": self._use_fallback,
            "consecutive_failures": self._consecutive_failures,
            "circuit_open": self._circuit_open,
            "current_backoff_secs": self._current_backoff,
            "primary_type": type(self._primary).__name__,
            "fallback_type": type(self._fallback).__name__,
        }

    async def _call(self, method_name: str, *args, **kwargs):
        async with self._lock:
            # Periodically retry primary when in fallback mode
            if self._use_fallback and not self._circuit_open:
                elapsed = time.monotonic() - self._last_primary_attempt
                if elapsed >= self._current_backoff:
                    self._last_primary_attempt = time.monotonic()
                    try:
                        method = getattr(self._primary, method_name)
                        result = await method(*args, **kwargs)
                        # Primary recovered — switch back and reset state
                        logger.info(
                            "Registry primary backend recovered after %d failure(s), "
                            "switching back from in-memory fallback",
                            self._consecutive_failures,
                        )
                        self._use_fallback = False
                        self._consecutive_failures = 0
                        self._current_backoff = _INITIAL_BACKOFF
                        self._circuit_open = False
                        return result
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        self._consecutive_failures += 1
                        self._current_backoff = min(
                            self._current_backoff * _BACKOFF_FACTOR, _MAX_BACKOFF
                        )
                        if self._consecutive_failures >= _CIRCUIT_BREAK_AFTER:
                            self._circuit_open = True
                            logger.warning(
                                "Registry circuit breaker OPEN after %d consecutive "
                                "failures — primary backend will not be retried until "
                                "manual intervention or restart. Last error: %s",
                                self._consecutive_failures,
                                exc,
                            )
                        else:
                            logger.debug(
                                "Primary registry retry %d/%d failed (next in %.0fs): %s",
                                self._consecutive_failures,
                                _CIRCUIT_BREAK_AFTER,
                                self._current_backoff,
                                exc,
                            )

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
                "Registry backend error (%s), switching to in-memory fallback. "
                "⚠ Job state will NOT persist across restarts. Error: %s",
                type(exc).__name__,
                exc,
            )
            async with self._lock:
                self._use_fallback = True
                self._consecutive_failures = 1
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
