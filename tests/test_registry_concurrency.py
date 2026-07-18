"""Tests for MemoryJobRegistry concurrency safety and deep copy isolation."""

import asyncio

import pytest

from ofx.runner import cleanup_registry
from ofx.runner.registry import MemoryJobRegistry

@pytest.fixture
async def registry():
    reg = MemoryJobRegistry()
    yield reg
    await cleanup_registry(reg)

@pytest.mark.asyncio
class TestDeepCopyIsolation:
    """Verify that stored values are isolated from external mutations."""

    async def test_set_isolates_from_caller(self, registry):
        """Mutating the original dict after set() must not affect the registry."""
        data = {"nested": {"secret": "original"}}
        await registry.set("k1", data)

        data["nested"]["secret"] = "mutated"

        stored = await registry.get("k1")
        assert stored["nested"]["secret"] == "original"

    async def test_get_returns_independent_copy(self, registry):
        """Two get() calls return independent copies."""
        await registry.set("k1", {"nested": {"val": 1}})

        copy_a = await registry.get("k1")
        copy_b = await registry.get("k1")

        copy_a["nested"]["val"] = 999
        assert copy_b["nested"]["val"] == 1

        stored = await registry.get("k1")
        assert stored["nested"]["val"] == 1

    async def test_update_does_not_share_references(self, registry):
        """After update(), changing the update dict must not affect stored data."""
        await registry.set("k1", {"a": 1})
        updates = {"b": {"deep": True}}
        await registry.update("k1", updates)

        updates["b"]["deep"] = False
        stored = await registry.get("k1")
        assert stored["b"]["deep"] is True

    async def test_get_all_returns_deep_copy(self, registry):
        """get_all() returns fully isolated data."""
        await registry.set("k1", {"nested": {"x": 42}})
        all_data = await registry.get_all()

        all_data["k1"]["nested"]["x"] = 0
        stored = await registry.get("k1")
        assert stored["nested"]["x"] == 42

    async def test_set_list_values_isolated(self, registry):
        """Lists stored in the registry are deep-copied too."""
        items = [{"host": "a"}, {"host": "b"}]
        await registry.set("k1", items)

        items[0]["host"] = "mutated"
        stored = await registry.get("k1")
        assert stored[0]["host"] == "a"

@pytest.mark.asyncio
class TestConcurrentAccess:
    """Verify that concurrent coroutines don't corrupt registry state."""

    async def test_concurrent_sets(self, registry):
        """Multiple concurrent set() calls should not lose data."""
        n = 100

        async def write(i: int):
            await registry.set(f"key-{i}", {"index": i})

        await asyncio.gather(*(write(i) for i in range(n)))

        for i in range(n):
            val = await registry.get(f"key-{i}")
            assert val is not None, f"key-{i} missing"
            assert val["index"] == i

    async def test_concurrent_updates(self, registry):
        """Concurrent updates to the same key should all apply."""
        await registry.set("counter", {"count": 0})
        n = 50

        async def increment(i: int):
            await registry.update("counter", {f"field_{i}": i})

        await asyncio.gather(*(increment(i) for i in range(n)))

        result = await registry.get("counter")
        for i in range(n):
            assert f"field_{i}" in result, f"field_{i} missing from result"

    async def test_concurrent_set_and_get(self, registry):
        """Concurrent reads and writes should not raise."""
        n = 100
        errors = []

        async def writer(i: int):
            try:
                await registry.set(f"key-{i}", {"data": i})
            except Exception as e:
                errors.append(e)

        async def reader(i: int):
            try:
                await registry.get(f"key-{i}")
            except Exception as e:
                errors.append(e)

        tasks = []
        for i in range(n):
            tasks.append(writer(i))
            tasks.append(reader(i))

        await asyncio.gather(*tasks)
        assert errors == [], f"Errors during concurrent access: {errors}"

    async def test_concurrent_delete(self, registry):
        """Concurrent deletes should not raise or corrupt state."""
        for i in range(50):
            await registry.set(f"key-{i}", {"data": i})

        async def delete(i: int):
            await registry.delete(f"key-{i}")

        await asyncio.gather(*(delete(i) for i in range(50)))

        all_data = await registry.get_all()
        assert len(all_data) == 0

@pytest.mark.asyncio
class TestUpdateAtomicity:
    """Verify update() performs atomic read-modify-write."""

    async def test_update_preserves_existing_fields(self, registry):
        """update() should merge, not replace."""
        await registry.set("k1", {"a": 1, "b": 2, "c": 3})
        await registry.update("k1", {"b": 20, "d": 4})

        result = await registry.get("k1")
        assert result == {"a": 1, "b": 20, "c": 3, "d": 4}

    async def test_update_nonexistent_key(self, registry):
        """update() on a missing key creates a new entry."""
        await registry.update("new_key", {"x": 1})
        result = await registry.get("new_key")
        assert result == {"x": 1}
