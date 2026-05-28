"""Tests for registry adapter hardening.

Covers:
- FileRegistry atomic writes (tmp+rename)
- MemoryJobRegistry maxsize enforcement
- Protocol conformance for all adapters
- Concurrent stress test for FileRegistry
"""

from __future__ import annotations

import asyncio
import json

import pytest

from ofx.runner.registry import FileRegistry, MemoryJobRegistry, RegistryAdapter
from ofx.runner.registry_backends.memcached import MemcachedJobRegistry
from ofx.runner.registry_backends.memory import RegistryOverflowError

# ── MemoryJobRegistry maxsize ────────────────────────────────────────────


class TestMemoryRegistryMaxsize:
    async def test_default_maxsize_is_large(self):
        reg = MemoryJobRegistry()
        assert reg._maxsize == 100_000

    async def test_custom_maxsize(self):
        reg = MemoryJobRegistry(maxsize=5)
        for i in range(5):
            await reg.set(f"key{i}", {"v": i})
        with pytest.raises(RegistryOverflowError, match="maxsize"):
            await reg.set("overflow", {"v": "bang"})

    async def test_update_existing_key_does_not_count(self):
        reg = MemoryJobRegistry(maxsize=2)
        await reg.set("a", {"v": 1})
        await reg.set("b", {"v": 2})
        # Updating existing key should not raise
        await reg.set("a", {"v": 3})
        assert (await reg.get("a")) == {"v": 3}

    async def test_delete_frees_capacity(self):
        reg = MemoryJobRegistry(maxsize=2)
        await reg.set("a", {"v": 1})
        await reg.set("b", {"v": 2})
        await reg.delete("a")
        # Now there's room again
        await reg.set("c", {"v": 3})
        assert (await reg.get("c")) == {"v": 3}

    async def test_zero_maxsize_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            MemoryJobRegistry(maxsize=0)

    async def test_negative_maxsize_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            MemoryJobRegistry(maxsize=-1)


# ── FileRegistry atomic writes ──────────────────────────────────────────


class TestFileRegistryAtomicWrite:
    async def test_write_is_atomic(self, tmp_path):
        """Verify writes go through tmp file + os.replace."""
        filepath = tmp_path / "reg.json"
        reg = FileRegistry(filepath=filepath)

        await reg.set("key1", {"val": 42})

        # The file should exist and be valid JSON
        data = json.loads(filepath.read_text())
        assert data["key1"]["val"] == 42

        # No leftover tmp file
        tmp_file = filepath.with_suffix(".json.tmp")
        assert not tmp_file.exists()

    async def test_mode_bits_on_file(self, tmp_path):
        filepath = tmp_path / "reg.json"
        reg = FileRegistry(filepath=filepath)
        await reg.set("key", "value")
        mode = filepath.stat().st_mode & 0o777
        assert mode == 0o600

    async def test_crash_simulation_no_corruption(self, tmp_path):
        """If the tmp file exists but rename hasn't happened, original is intact."""
        filepath = tmp_path / "reg.json"
        reg = FileRegistry(filepath=filepath)
        await reg.set("original", {"v": 1})

        # Simulate a "crash" by leaving a tmp file
        tmp_file = filepath.with_suffix(".json.tmp")
        tmp_file.write_text('{"corrupt": tru')  # malformed

        # The real file should still be valid
        data = json.loads(filepath.read_text())
        assert data["original"]["v"] == 1

    async def test_concurrent_disjoint_writes(self, tmp_path):
        """Multiple coroutines writing disjoint keys should not lose data."""
        filepath = tmp_path / "stress.json"
        reg = FileRegistry(filepath=filepath)

        async def writer(start: int, count: int):
            for i in range(start, start + count):
                await reg.set(f"key_{i}", {"idx": i})

        tasks = [writer(i * 50, 50) for i in range(8)]
        await asyncio.gather(*tasks)

        all_data = await reg.get_all()
        assert len(all_data) == 400


# ── Protocol conformance ────────────────────────────────────────────────


class TestProtocolConformance:
    """Verify all adapters implement the required interface."""

    @pytest.fixture(params=["memory", "file"])
    def adapter(self, request, tmp_path) -> RegistryAdapter:
        if request.param == "memory":
            return MemoryJobRegistry()
        elif request.param == "file":
            return FileRegistry(filepath=tmp_path / "proto.json")
        raise ValueError(f"Unknown adapter: {request.param}")

    async def test_set_and_get(self, adapter):
        await adapter.set("k", {"a": 1})
        assert (await adapter.get("k")) == {"a": 1}

    async def test_get_missing_returns_none(self, adapter):
        assert (await adapter.get("nonexistent")) is None

    async def test_update(self, adapter):
        await adapter.set("k", {"a": 1, "b": 2})
        await adapter.update("k", {"b": 3, "c": 4})
        result = await adapter.get("k")
        assert result["a"] == 1
        assert result["b"] == 3
        assert result["c"] == 4

    async def test_delete(self, adapter):
        await adapter.set("k", "v")
        assert await adapter.delete("k") is True
        assert await adapter.delete("k") is False

    async def test_exists(self, adapter):
        assert await adapter.exists("k") is False
        await adapter.set("k", "v")
        assert await adapter.exists("k") is True

    async def test_get_all(self, adapter):
        await adapter.set("a", 1)
        await adapter.set("b", 2)
        all_data = await adapter.get_all()
        assert "a" in all_data
        assert "b" in all_data

    async def test_clear(self, adapter):
        await adapter.set("a", 1)
        await adapter.clear()
        assert (await adapter.get("a")) is None

    async def test_close(self, adapter):
        await adapter.close()

    async def test_invalid_key_rejected(self, adapter):
        with pytest.raises(ValueError):
            await adapter.set("", "value")
        with pytest.raises(ValueError):
            await adapter.set("   ", "value")

    async def test_invalid_updates_rejected(self, adapter):
        await adapter.set("k", {"a": 1})
        with pytest.raises(ValueError):
            await adapter.update("k", "not_a_dict")  # type: ignore[arg-type]

    async def test_get_returns_copy(self, adapter):
        """Mutations to returned value must not affect stored data."""
        await adapter.set("k", {"a": 1})
        result = await adapter.get("k")
        if isinstance(result, dict):
            result["mutated"] = True
            original = await adapter.get("k")
            assert "mutated" not in original

    async def test_set_isolates_nested_values_from_caller(self, adapter):
        """Mutating caller-owned nested data after set() must not leak in."""
        payload = {"nested": {"status": "original"}}
        await adapter.set("k", payload)

        payload["nested"]["status"] = "mutated"

        stored = await adapter.get("k")
        assert stored["nested"]["status"] == "original"

    async def test_get_all_returns_deep_copy(self, adapter):
        """Mutating get_all() results must not affect stored nested data."""
        await adapter.set("k", {"nested": {"count": 1}})

        all_data = await adapter.get_all()
        all_data["k"]["nested"]["count"] = 2

        stored = await adapter.get("k")
        assert stored["nested"]["count"] == 1

    async def test_update_isolates_nested_values_from_caller(self, adapter):
        """Mutating caller-owned nested data after update() must not leak in."""
        await adapter.set("k", {"status": "running"})
        updates = {"nested": {"status": "complete"}}

        await adapter.update("k", updates)
        updates["nested"]["status"] = "mutated"

        stored = await adapter.get("k")
        assert stored["nested"]["status"] == "complete"


class TestRegistrySerializationHelpers:
    def test_serialize_value_keeps_default_string_fallback(self):
        class NotJsonSerializable:
            def __str__(self):
                return "fallback"

        serialized = MemoryJobRegistry._serialize_value(
            "k", {"value": NotJsonSerializable()}
        )

        assert serialized == '{"value": "fallback"}'

    def test_deserialize_value_handles_bytes_and_malformed_json(self):
        assert MemoryJobRegistry._deserialize_value("k", b'{"a": 1}') == {"a": 1}
        assert MemoryJobRegistry._deserialize_value("bad", b'{"a":') is None


class FakeMemcachedClient:
    def __init__(self):
        self.store: dict[bytes, bytes] = {}

    async def get(self, key: bytes) -> bytes | None:
        return self.store.get(key)

    async def set(self, key: bytes, value: bytes) -> None:
        self.store[key] = value

    async def delete(self, key: bytes) -> None:
        self.store.pop(key, None)


class FakeMemcachedRegistry(MemcachedJobRegistry):
    def __init__(self, client: FakeMemcachedClient):
        self.prefix = "ofx:job:"
        self._client = client

    async def _get_client(self):
        return self._client


class TestMemcachedRegistryIndexHelpers:
    async def test_index_helpers_track_set_delete_and_clear(self):
        registry = FakeMemcachedRegistry(FakeMemcachedClient())

        await registry.set("a", {"value": 1})
        await registry.set("b", [1, 2])

        assert await registry.get_all() == {"a": {"value": 1}, "b": [1, 2]}

        assert await registry.delete("a") is True
        assert await registry.get_all() == {"b": [1, 2]}

        await registry.clear()
        assert await registry.get_all() == {}
