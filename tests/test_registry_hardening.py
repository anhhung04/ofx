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


class TestRegistryAdapterWrapperHelpers:
    class _Adapter(RegistryAdapter):
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def _set(self, key: str, value):
            self.calls.append(("set", (key, value)))

        async def _get(self, key: str):
            self.calls.append(("get", key))
            return {"key": key}

        async def _update(self, key: str, updates):
            self.calls.append(("update", (key, updates)))

        async def _delete(self, key: str):
            self.calls.append(("delete", key))
            return True

        async def _exists(self, key: str):
            self.calls.append(("exists", key))
            return True

        async def _get_all(self):
            return {}

        async def _clear(self):
            return None

        async def _close(self):
            return None

    @pytest.mark.asyncio
    async def test_key_wrappers_validate_then_delegate(self):
        adapter = self._Adapter()

        assert await adapter.get("job") == {"key": "job"}
        await adapter.set("job", {"a": 1})
        assert await adapter.delete("job") is True
        assert await adapter.exists("job") is True

        assert adapter.calls == [
            ("get", "job"),
            ("set", ("job", {"a": 1})),
            ("delete", "job"),
            ("exists", "job"),
        ]

    @pytest.mark.asyncio
    async def test_update_wrapper_validates_key_and_updates(self):
        adapter = self._Adapter()

        await adapter.update("job", {"status": "done"})

        assert adapter.calls == [("update", ("job", {"status": "done"}))]


class TestRegistrySerializationHelpers:
    @pytest.mark.asyncio
    async def test_serialized_prefixed_registry_adapter_shares_crud_flow(self):
        from ofx.runner.registry_adapter import SerializedPrefixedRegistryAdapter

        class _Adapter(SerializedPrefixedRegistryAdapter):
            prefix = "ofx:job:"

            def __init__(self):
                self.storage: dict[str, str] = {}

            async def _read_storage_value(self, storage_key: str):
                return self.storage.get(storage_key)

            async def _write_storage_value(self, storage_key: str, json_value: str) -> None:
                self.storage[storage_key] = json_value

            async def _storage_key_exists(self, storage_key: str) -> bool:
                return storage_key in self.storage

            async def _delete_storage_key(self, storage_key: str) -> None:
                self.storage.pop(storage_key, None)

            async def _storage_entries(self):
                return [
                    (self._logical_key(key), value)
                    for key, value in self.storage.items()
                ]

            async def _clear_storage(self) -> None:
                self.storage.clear()

            async def _close(self) -> None:
                return None

        adapter = _Adapter()

        await adapter.set("job", {"status": "running"})
        assert await adapter.get("job") == {"status": "running"}

        await adapter.update("job", {"status": "done"})
        assert await adapter.get("job") == {"status": "done"}
        assert await adapter.exists("job") is True
        assert await adapter.get_all() == {"job": {"status": "done"}}

        assert await adapter.delete("job") is True
        assert await adapter.exists("job") is False

    @pytest.mark.asyncio
    async def test_serialized_prefixed_registry_adapter_runs_write_delete_hooks(self):
        from ofx.runner.registry_adapter import SerializedPrefixedRegistryAdapter

        class _Adapter(SerializedPrefixedRegistryAdapter):
            prefix = "ofx:job:"

            def __init__(self):
                self.storage: dict[str, str] = {}
                self.events: list[tuple[str, str]] = []

            async def _read_storage_value(self, storage_key: str):
                return self.storage.get(storage_key)

            async def _write_storage_value(self, storage_key: str, json_value: str) -> None:
                self.storage[storage_key] = json_value

            async def _storage_key_exists(self, storage_key: str) -> bool:
                return storage_key in self.storage

            async def _delete_storage_key(self, storage_key: str) -> None:
                self.storage.pop(storage_key, None)

            async def _storage_entries(self):
                return []

            async def _clear_storage(self) -> None:
                self.storage.clear()

            async def _after_storage_write(self, key: str) -> None:
                self.events.append(("write", key))

            async def _after_storage_delete(self, key: str) -> None:
                self.events.append(("delete", key))

            async def _close(self) -> None:
                return None

        adapter = _Adapter()

        await adapter.set("job", {"status": "running"})
        await adapter.update("job", {"status": "done"})
        await adapter.delete("job")

        assert adapter.events == [("write", "job"), ("write", "job"), ("delete", "job")]

    def test_backend_logging_helpers_use_display_name_and_actions(self, monkeypatch):
        from ofx.runner.registry_adapter import RegistryAdapter

        class _Adapter(RegistryAdapter):
            _backend_display_name = "CustomRegistry"

            async def _set(self, key: str, value): ...
            async def _get(self, key: str): ...
            async def _update(self, key: str, updates): ...
            async def _delete(self, key: str): ...
            async def _exists(self, key: str): ...
            async def _get_all(self): ...
            async def _clear(self): ...
            async def _close(self): ...

        messages: list[str] = []
        adapter = _Adapter()
        monkeypatch.setattr(adapter, "_log_debug", messages.append)

        adapter._log_backend_initialized("at somewhere")
        adapter._log_backend_key_action("Set", "job-a")
        adapter._log_backend_action("Closed")

        assert messages == [
            "Initialized CustomRegistry at somewhere",
            "Set key 'job-a' in CustomRegistry",
            "Closed CustomRegistry",
        ]

    def test_prefix_helpers_normalize_and_strip_keys(self):
        assert MemoryJobRegistry._normalized_prefix("/ofx/job", "/") == "/ofx/job/"
        assert MemoryJobRegistry._prefixed_key("ofx:job:", "abc") == "ofx:job:abc"
        assert MemoryJobRegistry._unprefixed_key("/ofx/job/abc", "/ofx/job", "/") == "abc"

    def test_decoded_mapping_skips_empty_and_invalid_entries(self):
        entries = [
            ("a", '{"v": 1}'),
            ("b", None),
            ("c", '{"bad"'),
        ]

        decoded = MemoryJobRegistry._decoded_mapping(entries)

        assert decoded == {"a": {"v": 1}}

    def test_prefixed_registry_helpers_build_and_strip_storage_keys(self):
        from ofx.runner.registry_adapter import PrefixedRegistryAdapter

        class _Adapter(PrefixedRegistryAdapter):
            prefix = "/ofx/job"
            _prefix_separator = "/"

            async def _set(self, key: str, value): ...
            async def _get(self, key: str): ...
            async def _update(self, key: str, updates): ...
            async def _delete(self, key: str): ...
            async def _exists(self, key: str): ...
            async def _get_all(self): ...
            async def _clear(self): ...
            async def _close(self): ...

        adapter = _Adapter()

        assert adapter._storage_prefix() == "/ofx/job/"
        assert adapter._storage_key("abc") == "/ofx/job/abc"
        assert adapter._logical_key("/ofx/job/abc") == "abc"

    def test_merged_updated_value_merges_dicts_with_copies(self):
        existing = {"a": 1, "nested": {"x": 1}}
        updates = {"b": 2, "nested": {"x": 9}}

        merged = MemoryJobRegistry._merged_updated_value(existing, updates)

        assert merged == {"a": 1, "b": 2, "nested": {"x": 9}}
        updates["nested"]["x"] = 0
        assert merged["nested"]["x"] == 9

    def test_merged_updated_value_replaces_non_dict_existing(self):
        merged = MemoryJobRegistry._merged_updated_value([1, 2], {"a": 1})

        assert merged == {"a": 1}

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
    async def test_key_byte_helpers_use_prefixed_keys(self):
        registry = FakeMemcachedRegistry(FakeMemcachedClient())

        assert registry._cache_key_bytes("a") == b"ofx:job:a"
        assert registry._index_key_bytes() == b"ofx:job:_index"

    async def test_index_helpers_track_set_delete_and_clear(self):
        registry = FakeMemcachedRegistry(FakeMemcachedClient())

        await registry.set("a", {"value": 1})
        await registry.set("b", [1, 2])

        assert await registry.get_all() == {"a": {"value": 1}, "b": [1, 2]}

        assert await registry.delete("a") is True
        assert await registry.get_all() == {"b": [1, 2]}

        await registry.clear()
        assert await registry.get_all() == {}
