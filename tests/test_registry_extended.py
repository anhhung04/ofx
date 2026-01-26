"""Tests for optional registry backends."""

from __future__ import annotations

import importlib

import pytest

from ofx.runner.core import RegistryFactory


def _can_import(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except Exception:
        return False


async def _assert_basic_operations(registry) -> None:
    test_data = {"name": "test-job", "status": "running"}

    await registry.set("job1", test_data)
    result = await registry.get("job1")
    assert result == test_data

    await registry.update("job1", {"status": "completed"})
    result = await registry.get("job1")
    assert result["status"] == "completed"

    assert await registry.exists("job1") is True
    assert await registry.exists("nonexistent") is False

    deleted = await registry.delete("job1")
    assert deleted is True
    assert await registry.get("job1") is None


class TestMemcachedJobRegistry:
    """Test suite for MemcachedJobRegistry"""

    @pytest.mark.asyncio
    async def test_memcached_import_error(self):
        """Test that MemcachedJobRegistry raises ImportError when aiomcache is not installed"""
        if _can_import("aiomcache"):
            pytest.skip("aiomcache is installed, skipping import error test")

        with pytest.raises(ImportError, match="aiomcache"):
            RegistryFactory.create_memcached()

    @pytest.mark.asyncio
    async def test_memcached_basic_operations(self):
        """Test basic Memcached operations if aiomcache is available"""
        if not _can_import("aiomcache"):
            pytest.skip("aiomcache not installed")

        try:
            registry = RegistryFactory.create_memcached()
            await _assert_basic_operations(registry)
            await registry.close()
        except Exception as e:
            # Connection errors are expected if Memcached server is not running
            if "Connection refused" in str(e) or "ECONNREFUSED" in str(e):
                pytest.skip("Memcached server not available")
            raise


class TestEtcdJobRegistry:
    """Test suite for EtcdJobRegistry"""

    @pytest.mark.asyncio
    async def test_etcd_import_error(self):
        """Test that EtcdJobRegistry raises ImportError when etcd3 is not installed"""
        if _can_import("etcd3"):
            pytest.skip("etcd3 is installed, skipping import error test")

        with pytest.raises(ImportError, match="etcd3"):
            RegistryFactory.create_etcd()

    @pytest.mark.asyncio
    async def test_etcd_basic_operations(self):
        """Test basic etcd operations if etcd3 is available"""
        if not _can_import("etcd3"):
            pytest.skip("etcd3 not installed or incompatible")

        try:
            registry = RegistryFactory.create_etcd()
            await _assert_basic_operations(registry)
            await registry.close()
        except Exception as e:
            # Connection errors are expected if etcd server is not running
            if "Connection refused" in str(e) or "ECONNREFUSED" in str(e):
                pytest.skip("etcd server not available")
            raise


class TestRegistryFactoryExtended:
    """Test factory with new backends"""

    def test_factory_supports_memcached(self):
        """Test that factory recognizes memcached backend"""
        if _can_import("aiomcache"):
            registry = RegistryFactory.create_memcached()
            assert registry.__class__.__name__ == "MemcachedJobRegistry"
        else:
            with pytest.raises(ImportError, match="aiomcache"):
                RegistryFactory.create_memcached()

    def test_factory_supports_etcd(self):
        """Test that factory recognizes etcd backend"""
        if _can_import("etcd3"):
            registry = RegistryFactory.create_etcd()
            assert registry.__class__.__name__ == "EtcdJobRegistry"
        else:
            with pytest.raises(ImportError, match="etcd3"):
                RegistryFactory.create_etcd()

    def test_invalid_backend_error_message(self):
        """Test that invalid backend raises ValueError with helpful message"""
        with pytest.raises(ValueError) as exc_info:
            RegistryFactory.create("invalid_backend")

        assert "memcached" in str(exc_info.value)
        assert "etcd" in str(exc_info.value)
        assert "Supported backends" in str(exc_info.value)
