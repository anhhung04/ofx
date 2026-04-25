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

from ofx.runner.registry.base import RegistryAdapter
from ofx.runner.registry.file import FileRegistry
from ofx.runner.registry.memory import MemoryJobRegistry, RegistryOverflowError

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
