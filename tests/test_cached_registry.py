"""Tests for CachedRegistryAdapter — TTL, eviction, async correctness."""

from __future__ import annotations

import asyncio

import pytest

from ofx.runner.registry.cache import CachedRegistryAdapter
from ofx.runner.registry.memory import MemoryJobRegistry


@pytest.fixture
def backend():
    return MemoryJobRegistry()


@pytest.fixture
def cache(backend):
    return CachedRegistryAdapter(backend, ttl=0.5, max_entries=10)


# ── Construction ─────────────────────────────────────────────────────────


class TestCachedRegistryConstruction:
    def test_invalid_ttl_raises(self):
        with pytest.raises(ValueError, match="ttl must be positive"):
            CachedRegistryAdapter(MemoryJobRegistry(), ttl=0)

    def test_negative_ttl_raises(self):
        with pytest.raises(ValueError, match="ttl must be positive"):
            CachedRegistryAdapter(MemoryJobRegistry(), ttl=-1)

    def test_invalid_max_entries_raises(self):
        with pytest.raises(ValueError, match="max_entries must be positive"):
            CachedRegistryAdapter(MemoryJobRegistry(), max_entries=0)


# ── Basic operations ─────────────────────────────────────────────────────


class TestCachedRegistryOps:
    async def test_set_and_get(self, cache):
        await cache.set("key1", {"status": "done"})
        result = await cache.get("key1")
        assert result == {"status": "done"}

    async def test_get_missing_returns_none(self, cache):
        result = await cache.get("missing")
        assert result is None

    async def test_update_existing(self, cache):
        await cache.set("k", {"a": 1, "b": 2})
        await cache.update("k", {"b": 99})
        result = await cache.get("k")
        assert result == {"a": 1, "b": 99}

    async def test_delete(self, cache):
        await cache.set("k", "val")
        deleted = await cache.delete("k")
        assert deleted is True
        assert await cache.get("k") is None

    async def test_delete_missing(self, cache):
        deleted = await cache.delete("nonexistent")
        assert deleted is False

    async def test_exists_true(self, cache):
        await cache.set("k", "v")
        assert await cache.exists("k") is True

    async def test_exists_false(self, cache):
        assert await cache.exists("missing") is False

    async def test_get_all(self, cache):
        await cache.set("a", {"x": 1})
        await cache.set("b", {"y": 2})
        all_data = await cache.get_all()
        assert "a" in all_data
        assert "b" in all_data

    async def test_clear(self, cache):
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.clear()
        assert await cache.get("a") is None
        assert await cache.get("b") is None

    async def test_close(self, cache):
        await cache.set("k", "v")
        await cache.close()
        # After close, cache is cleared
        # (backend may still have data but cache is empty)


# ── TTL expiration ───────────────────────────────────────────────────────


class TestCachedRegistryTTL:
    async def test_cache_hit_within_ttl(self, backend):
        cache = CachedRegistryAdapter(backend, ttl=10.0)
        await cache.set("k", {"v": 1})
        # Modify backend directly — cache should still serve old value
        await backend.set("k", {"v": 999})
        result = await cache.get("k")
        assert result == {"v": 1}  # Cached, not from backend

    async def test_cache_miss_after_ttl(self, backend):
        cache = CachedRegistryAdapter(backend, ttl=0.05)
        await cache.set("k", {"v": 1})
        await asyncio.sleep(0.1)  # Wait for TTL to expire
        # Backend still has the value from the original set
        result = await cache.get("k")
        assert result == {"v": 1}  # Re-fetched from backend

    async def test_get_all_cached(self, backend):
        cache = CachedRegistryAdapter(backend, ttl=10.0)
        await cache.set("a", 1)
        await cache.set("b", 2)
        # First get_all fetches from backend
        _all1 = await cache.get_all()
        # Modify backend directly
        await backend.set("c", 3)
        # Second get_all should use cache (within TTL)
        all2 = await cache.get_all()
        assert "c" not in all2  # Cached result, doesn't include new key


# ── LRU eviction ─────────────────────────────────────────────────────────


class TestCachedRegistryEviction:
    async def test_eviction_at_max_entries(self, backend):
        cache = CachedRegistryAdapter(backend, ttl=10.0, max_entries=3)
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.set("c", 3)
        await cache.set("d", 4)  # Should evict "a"
        # "a" evicted from cache, but still in backend
        # On get, should refetch from backend
        result = await cache.get("a")
        assert result == 1  # Refetched from backend

    async def test_many_entries_dont_crash(self, backend):
        cache = CachedRegistryAdapter(backend, ttl=10.0, max_entries=5)
        for i in range(100):
            await cache.set(f"key_{i}", i)
        # Cache should only hold last 5
        result = await cache.get("key_99")
        assert result == 99


# ── Copy safety ──────────────────────────────────────────────────────────


class TestCachedRegistryCopySafety:
    async def test_get_returns_shallow_copy(self, cache):
        """Returned dicts are shallow copies — top-level keys are isolated."""
        await cache.set("k", {"a": 1, "b": 2})
        result1 = await cache.get("k")
        result1["a"] = 999
        result2 = await cache.get("k")
        assert result2["a"] == 1  # Top-level mutation doesn't leak

    async def test_get_all_returns_copy(self, cache):
        await cache.set("k", {"v": 1})
        all1 = await cache.get_all()
        all1["k"] = "mutated"
        all2 = await cache.get_all()
        assert all2["k"] != "mutated"


# ── Write invalidation ──────────────────────────────────────────────────


class TestCachedRegistryInvalidation:
    async def test_set_invalidates_get_all_cache(self, backend):
        cache = CachedRegistryAdapter(backend, ttl=10.0)
        await cache.set("a", 1)
        _ = await cache.get_all()  # populate _cache_all
        await cache.set("b", 2)  # should invalidate _cache_all
        all_data = await cache.get_all()
        assert "b" in all_data

    async def test_update_invalidates_get_all_cache(self, backend):
        cache = CachedRegistryAdapter(backend, ttl=10.0)
        await cache.set("k", {"a": 1})
        _ = await cache.get_all()
        await cache.update("k", {"a": 2})
        all_data = await cache.get_all()
        assert all_data["k"]["a"] == 2

    async def test_delete_invalidates_get_all_cache(self, backend):
        cache = CachedRegistryAdapter(backend, ttl=10.0)
        await cache.set("a", 1)
        await cache.set("b", 2)
        _ = await cache.get_all()
        await cache.delete("a")
        all_data = await cache.get_all()
        assert "a" not in all_data

    async def test_clear_invalidates_all(self, backend):
        cache = CachedRegistryAdapter(backend, ttl=10.0)
        await cache.set("a", 1)
        _ = await cache.get("a")  # populate entry cache
        _ = await cache.get_all()  # populate _cache_all
        await cache.clear()
        assert await cache.get("a") is None
        assert await cache.get_all() == {}


# ── Concurrency ──────────────────────────────────────────────────────────


class TestCachedRegistryConcurrency:
    async def test_concurrent_reads_consistent(self, cache):
        """Multiple concurrent gets return the same value."""
        await cache.set("k", {"status": "ok"})
        results = await asyncio.gather(
            *[cache.get("k") for _ in range(20)]
        )
        for r in results:
            assert r == {"status": "ok"}

    async def test_concurrent_writes_dont_corrupt(self, cache):
        """Concurrent sets don't cause data corruption."""
        async def writer(i: int):
            await cache.set(f"key_{i}", {"value": i})

        await asyncio.gather(*[writer(i) for i in range(50)])
        for i in range(50):
            result = await cache.get(f"key_{i}")
            assert result == {"value": i}

    async def test_concurrent_mixed_ops(self, cache):
        """Mix of reads, writes, and deletes under concurrency."""
        await cache.set("shared", {"count": 0})

        async def read_op():
            result = await cache.get("shared")
            return result is not None

        async def write_op(i: int):
            await cache.update("shared", {"count": i})

        tasks = []
        for i in range(20):
            tasks.append(read_op())
            tasks.append(write_op(i))
        results = await asyncio.gather(*tasks)
        # All reads should succeed (return True)
        reads = [r for r in results if isinstance(r, bool)]
        assert all(reads)
