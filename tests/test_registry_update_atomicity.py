"""Regression tests for atomic registry read-modify-write updates.

Covers findings M7 (non-atomic ``_update`` on serialized backends and
FileRegistry) and L7 (MemoryJobRegistry capacity check on new-key updates).

Each test fails against the pre-fix code and passes after the fix.
"""

from __future__ import annotations

import asyncio

import pytest

from ofx.runner.registry import FileRegistry, MemoryJobRegistry
from ofx.runner.registry_adapter import SerializedPrefixedRegistryAdapter
from ofx.runner.registry_backends.memory import RegistryOverflowError


class _SlowSerializedAdapter(SerializedPrefixedRegistryAdapter):
    """Serialized-prefix adapter backed by an in-memory dict with latency.

    The artificial delay widens the read→write window so concurrent updates
    deterministically interleave when no lock guards the read-modify-write.
    """

    prefix = "test:"

    def __init__(self, delay: float = 0.02):
        self.storage: dict[str, str] = {}
        self.delay = delay

    async def _read_storage_value(self, storage_key: str) -> str | bytes | None:
        await asyncio.sleep(self.delay)
        return self.storage.get(storage_key)

    async def _write_storage_value(self, storage_key: str, json_value: str) -> None:
        await asyncio.sleep(self.delay)
        self.storage[storage_key] = json_value

    async def _storage_key_exists(self, storage_key: str) -> bool:
        return storage_key in self.storage

    async def _delete_storage_key(self, storage_key: str) -> None:
        self.storage.pop(storage_key, None)

    async def _storage_entries(self) -> list[tuple[str, str | bytes | None]]:
        return [
            (self._logical_key(key), value)
            for key, value in self.storage.items()
        ]

    async def _clear_storage(self) -> None:
        self.storage.clear()

    async def _close(self) -> None:
        return None


@pytest.mark.asyncio
class TestSerializedAdapterAtomicUpdate:
    """M7: ``_update`` must be an atomic read-modify-write per instance."""

    async def test_concurrent_updates_to_same_key_apply_all_fields(self):
        adapter = _SlowSerializedAdapter(delay=0.02)
        await adapter.set("job", {"status": "running"})
        n = 20

        async def update(i: int) -> None:
            await adapter.update("job", {f"field_{i}": i})

        await asyncio.gather(*(update(i) for i in range(n)))

        result = await adapter.get("job")
        assert result["status"] == "running"
        for i in range(n):
            assert f"field_{i}" in result, f"field_{i} lost by concurrent update"

    async def test_update_lock_is_per_instance(self):
        """Two instances must not share a lock (parallel backends stay isolated)."""
        first = _SlowSerializedAdapter(delay=0.0)
        second = _SlowSerializedAdapter(delay=0.0)
        assert first._get_update_lock() is not second._get_update_lock()


@pytest.mark.asyncio
class TestFileRegistryAtomicUpdate:
    """M7: FileRegistry must hold its filelock across read+write."""

    async def test_update_holds_filelock_during_read(self, tmp_path):
        registry = FileRegistry(filepath=tmp_path / "registry.json")
        await registry.set("job", {"status": "running"})

        observed: dict[str, bool] = {}
        original_read = registry._read_registry

        async def tracked_read() -> dict:
            observed["lock_held_during_read"] = registry._lock.is_locked
            return await original_read()

        registry._read_registry = tracked_read
        await registry.update("job", {"status": "done"})

        assert observed["lock_held_during_read"] is True, (
            "filelock was not held while reading during update()"
        )
        assert (await registry.get("job")) == {"status": "done"}

    async def test_set_holds_filelock_during_read(self, tmp_path):
        registry = FileRegistry(filepath=tmp_path / "registry.json")
        await registry.set("job", {"status": "running"})

        observed: dict[str, bool] = {}
        original_read = registry._read_registry

        async def tracked_read() -> dict:
            observed["lock_held_during_read"] = registry._lock.is_locked
            return await original_read()

        registry._read_registry = tracked_read
        await registry.set("other", {"status": "queued"})

        assert observed["lock_held_during_read"] is True, (
            "filelock was not held while reading during set()"
        )

    async def test_concurrent_updates_to_same_key_apply_all_fields(self, tmp_path):
        """Stress: no field may be lost when many coroutines update one key."""
        registry = FileRegistry(filepath=tmp_path / "registry.json")
        await registry.set("job", {"status": "running"})
        n = 40

        async def update(i: int) -> None:
            await registry.update("job", {f"field_{i}": i})

        await asyncio.gather(*(update(i) for i in range(n)))

        result = await registry.get("job")
        for i in range(n):
            assert f"field_{i}" in result, f"field_{i} lost by concurrent update"

    async def test_cross_instance_updates_do_not_lose_fields(self, tmp_path):
        """Two registry instances on one file must not lose updates (M7)."""
        filepath = tmp_path / "registry.json"
        first = FileRegistry(filepath=filepath)
        second = FileRegistry(filepath=filepath)
        try:
            await first.set("job", {"status": "running"})
            n = 30

            async def update_a(i: int) -> None:
                await first.update("job", {f"a_{i}": i})

            async def update_b(i: int) -> None:
                await second.update("job", {f"b_{i}": i})

            await asyncio.gather(
                *(update_a(i) for i in range(n)),
                *(update_b(i) for i in range(n)),
            )

            result = await first.get("job")
            for i in range(n):
                assert f"a_{i}" in result, f"a_{i} lost by cross-instance update"
                assert f"b_{i}" in result, f"b_{i} lost by cross-instance update"
        finally:
            await first._close()
            await second._close()


@pytest.mark.asyncio
class TestMemoryRegistryUpdateCapacity:
    """L7: ``_update`` must enforce maxsize when the key is new."""

    async def test_update_new_key_respects_maxsize(self):
        registry = MemoryJobRegistry(maxsize=1)
        await registry.set("existing", {"v": 1})

        with pytest.raises(RegistryOverflowError, match="maxsize"):
            await registry.update("new", {"v": 2})

        assert (await registry.get("existing")) == {"v": 1}

    async def test_update_existing_key_at_capacity_is_allowed(self):
        registry = MemoryJobRegistry(maxsize=1)
        await registry.set("k", {"v": 1})
        await registry.update("k", {"v": 2})
        assert (await registry.get("k")) == {"v": 2}
