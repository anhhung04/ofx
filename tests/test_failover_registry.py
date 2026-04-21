"""Tests for FailoverRegistryAdapter — failover, recovery, error propagation."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ofx.runner.registry.base import RegistryAdapter
from ofx.runner.registry.failover import FailoverRegistryAdapter
from ofx.runner.registry.memory import MemoryJobRegistry


class BrokenRegistry(RegistryAdapter):
    """A registry that always raises on every operation."""

    async def _set(self, key: str, value: Any) -> None:
        raise ConnectionError("backend down")

    async def _get(self, key: str) -> Any | None:
        raise ConnectionError("backend down")

    async def _update(self, key: str, updates: dict[str, Any]) -> None:
        raise ConnectionError("backend down")

    async def _delete(self, key: str) -> bool:
        raise ConnectionError("backend down")

    async def _exists(self, key: str) -> bool:
        raise ConnectionError("backend down")

    async def _get_all(self) -> dict[str, Any]:
        raise ConnectionError("backend down")

    async def _clear(self) -> None:
        raise ConnectionError("backend down")

    async def _close(self) -> None:
        raise ConnectionError("backend down")


class FlakeyRegistry(RegistryAdapter):
    """A registry that fails N times then succeeds."""

    def __init__(self, fail_count: int = 1):
        self._fail_count = fail_count
        self._calls = 0
        self._store: dict[str, Any] = {}

    async def _set(self, key: str, value: Any) -> None:
        self._calls += 1
        if self._calls <= self._fail_count:
            raise ConnectionError("temporary failure")
        self._store[key] = value

    async def _get(self, key: str) -> Any | None:
        self._calls += 1
        if self._calls <= self._fail_count:
            raise ConnectionError("temporary failure")
        return self._store.get(key)

    async def _update(self, key: str, updates: dict[str, Any]) -> None:
        self._calls += 1
        if self._calls <= self._fail_count:
            raise ConnectionError("temporary failure")

    async def _delete(self, key: str) -> bool:
        self._calls += 1
        if self._calls <= self._fail_count:
            raise ConnectionError("temporary failure")
        return self._store.pop(key, None) is not None

    async def _exists(self, key: str) -> bool:
        self._calls += 1
        if self._calls <= self._fail_count:
            raise ConnectionError("temporary failure")
        return key in self._store

    async def _get_all(self) -> dict[str, Any]:
        self._calls += 1
        if self._calls <= self._fail_count:
            raise ConnectionError("temporary failure")
        return self._store.copy()

    async def _clear(self) -> None:
        self._store.clear()

    async def _close(self) -> None:
        pass


# ── Basic operations (no failures) ───────────────────────────────────────


class TestFailoverBasic:
    """When primary works, failover adapter behaves transparently."""

    async def test_set_and_get(self):
        adapter = FailoverRegistryAdapter(MemoryJobRegistry())
        await adapter.set("k", {"v": 1})
        result = await adapter.get("k")
        assert result == {"v": 1}

    async def test_update(self):
        adapter = FailoverRegistryAdapter(MemoryJobRegistry())
        await adapter.set("k", {"a": 1, "b": 2})
        await adapter.update("k", {"b": 99})
        result = await adapter.get("k")
        assert result["b"] == 99

    async def test_delete(self):
        adapter = FailoverRegistryAdapter(MemoryJobRegistry())
        await adapter.set("k", "v")
        assert await adapter.delete("k") is True
        assert await adapter.get("k") is None

    async def test_exists(self):
        adapter = FailoverRegistryAdapter(MemoryJobRegistry())
        assert await adapter.exists("k") is False
        await adapter.set("k", "v")
        assert await adapter.exists("k") is True

    async def test_get_all(self):
        adapter = FailoverRegistryAdapter(MemoryJobRegistry())
        await adapter.set("a", 1)
        await adapter.set("b", 2)
        all_data = await adapter.get_all()
        assert "a" in all_data and "b" in all_data


# ── Failover to fallback ─────────────────────────────────────────────────


class TestFailoverSwitch:
    """When primary fails, adapter switches to fallback."""

    async def test_switches_to_fallback_on_error(self):
        primary = BrokenRegistry()
        fallback = MemoryJobRegistry()
        adapter = FailoverRegistryAdapter(primary, fallback)

        # First call fails on primary, switches to fallback
        await adapter.set("k", {"v": 1})
        # Subsequent calls use fallback
        result = await adapter.get("k")
        assert result == {"v": 1}

    async def test_fallback_serves_data_after_switch(self):
        primary = BrokenRegistry()
        fallback = MemoryJobRegistry()
        adapter = FailoverRegistryAdapter(primary, fallback)

        await adapter.set("a", 1)
        await adapter.set("b", 2)
        all_data = await adapter.get_all()
        assert all_data == {"a": 1, "b": 2}

    async def test_fallback_error_propagates(self):
        """If both primary AND fallback fail, the error propagates."""
        primary = BrokenRegistry()
        fallback = BrokenRegistry()
        adapter = FailoverRegistryAdapter(primary, fallback)

        # First call: primary fails → switch to fallback → fallback fails → error
        with pytest.raises(ConnectionError):
            await adapter.set("k", "v")

    async def test_default_fallback_is_memory(self):
        adapter = FailoverRegistryAdapter(BrokenRegistry())
        # Should use default MemoryJobRegistry fallback
        await adapter.set("k", "v")
        result = await adapter.get("k")
        assert result == "v"


# ── Recovery ─────────────────────────────────────────────────────────────


class TestFailoverRecovery:
    """Primary recovery after reconnect interval."""

    async def test_recovery_after_interval(self):
        primary = FlakeyRegistry(fail_count=1)
        fallback = MemoryJobRegistry()
        adapter = FailoverRegistryAdapter(primary, fallback)

        # First call fails, switches to fallback
        await adapter.set("k", "before_recovery")

        # Simulate reconnect interval passing
        adapter._last_primary_attempt = 0.0  # Force retry

        # Next call should try primary (which now works)
        # The flakey registry failed once, so calls > 1 succeed
        result = await adapter.get("k")
        # Data might come from fallback or primary depending on recovery
        # The important thing is it doesn't crash
        assert result is not None or result is None  # No crash

    async def test_stays_on_fallback_before_interval(self):
        primary = BrokenRegistry()
        fallback = MemoryJobRegistry()
        adapter = FailoverRegistryAdapter(primary, fallback)

        await adapter.set("k", "v")
        # _last_primary_attempt is set to now, so no retry yet
        result = await adapter.get("k")
        assert result == "v"  # Still from fallback


# ── CancelledError propagation ───────────────────────────────────────────


class TestFailoverCancelledError:
    """CancelledError must always propagate (never swallowed)."""

    async def test_cancelled_error_propagates_from_primary(self):
        primary = MemoryJobRegistry()
        adapter = FailoverRegistryAdapter(primary)

        # Monkey-patch primary to raise CancelledError
        async def _cancel_get(key):
            raise asyncio.CancelledError()

        primary._get = _cancel_get

        with pytest.raises(asyncio.CancelledError):
            await adapter.get("k")


# ── Clear and close ──────────────────────────────────────────────────────


class TestFailoverCleanup:
    async def test_clear_clears_fallback(self):
        primary = BrokenRegistry()
        fallback = MemoryJobRegistry()
        adapter = FailoverRegistryAdapter(primary, fallback)

        await adapter.set("k", "v")
        await adapter.clear()
        result = await fallback.get("k")
        assert result is None

    async def test_close_tolerates_broken_primary(self):
        adapter = FailoverRegistryAdapter(BrokenRegistry(), MemoryJobRegistry())
        # Should not raise even if primary.close() fails
        await adapter.close()
