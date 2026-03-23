"""Tests for job registry adapters"""

import tempfile
from pathlib import Path

import pytest

from ofx.runner.core import RegistryFactory, cleanup_registry
from ofx.runner.registry import (
    FileRegistry,
    MemoryJobRegistry,
)
from ofx.runner.registry.base import RegistryAdapter


@pytest.fixture
async def memory_registry():
    """Fixture for memory-based registry"""
    registry = MemoryJobRegistry()
    yield registry
    await cleanup_registry(registry)


@pytest.fixture
async def file_registry():
    """Fixture for file-based registry"""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        filepath = Path(f.name)

    registry = FileRegistry(filepath=filepath)
    yield registry
    await cleanup_registry(registry)

    # Clean up test file
    if filepath.exists():
        filepath.unlink()
    lockfile = filepath.with_suffix(".lock")
    if lockfile.exists():
        lockfile.unlink()


@pytest.mark.asyncio
class TestMemoryJobRegistry:
    """Test suite for MemoryJobRegistry"""

    async def test_set_and_get(self, memory_registry):
        """Test setting and getting job data"""
        job_data = {"name": "test-job", "status": "running", "steps": []}
        await memory_registry.set("job1", job_data)

        result = await memory_registry.get("job1")
        assert result == job_data

    async def test_get_nonexistent(self, memory_registry):
        """Test getting non-existent job returns None"""
        result = await memory_registry.get("nonexistent")
        assert result is None

    async def test_update(self, memory_registry):
        """Test updating job data"""
        job_data = {"name": "test-job", "status": "running"}
        await memory_registry.set("job1", job_data)

        await memory_registry.update("job1", {"status": "completed"})
        result = await memory_registry.get("job1")

        assert result["status"] == "completed"
        assert result["name"] == "test-job"

    async def test_delete(self, memory_registry):
        """Test deleting job data"""
        job_data = {"name": "test-job", "status": "running"}
        await memory_registry.set("job1", job_data)

        deleted = await memory_registry.delete("job1")
        assert deleted is True

        result = await memory_registry.get("job1")
        assert result is None

    async def test_delete_nonexistent(self, memory_registry):
        """Test deleting non-existent job returns False"""
        deleted = await memory_registry.delete("nonexistent")
        assert deleted is False

    async def test_exists(self, memory_registry):
        """Test checking job existence"""
        job_data = {"name": "test-job"}
        await memory_registry.set("job1", job_data)

        assert await memory_registry.exists("job1") is True
        assert await memory_registry.exists("nonexistent") is False

    async def test_get_all(self, memory_registry):
        """Test getting all jobs"""
        job1 = {"name": "job1", "status": "running"}
        job2 = {"name": "job2", "status": "completed"}

        await memory_registry.set("job1", job1)
        await memory_registry.set("job2", job2)

        all_jobs = await memory_registry.get_all()
        assert len(all_jobs) == 2
        assert all_jobs["job1"] == job1
        assert all_jobs["job2"] == job2

    async def test_clear(self, memory_registry):
        """Test clearing all jobs"""
        await memory_registry.set("job1", {"name": "job1"})
        await memory_registry.set("job2", {"name": "job2"})

        await memory_registry.clear()
        all_jobs = await memory_registry.get_all()
        assert len(all_jobs) == 0


@pytest.mark.asyncio
class TestFileJobRegistry:
    """Test suite for FileJobRegistry"""

    async def test_set_and_get(self, file_registry):
        """Test setting and getting job data"""
        job_data = {"name": "test-job", "status": "running", "steps": []}
        await file_registry.set("job1", job_data)

        result = await file_registry.get("job1")
        assert result == job_data

    async def test_persistence(self):
        """Test that data persists across registry instances"""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            filepath = Path(f.name)

        try:
            # First registry instance
            registry1 = FileRegistry(filepath=filepath)
            await registry1.set("job1", {"name": "persistent-job"})
            await cleanup_registry(registry1)

            # Second registry instance
            registry2 = FileRegistry(filepath=filepath)
            result = await registry2.get("job1")
            assert result["name"] == "persistent-job"
            await cleanup_registry(registry2)

        finally:
            if filepath.exists():
                filepath.unlink()
            lockfile = filepath.with_suffix(".lock")
            if lockfile.exists():
                lockfile.unlink()

    async def test_update(self, file_registry):
        """Test updating job data"""
        job_data = {"name": "test-job", "status": "running"}
        await file_registry.set("job1", job_data)

        await file_registry.update("job1", {"status": "completed"})
        result = await file_registry.get("job1")

        assert result["status"] == "completed"
        assert result["name"] == "test-job"

    async def test_get_all(self, file_registry):
        """Test getting all jobs"""
        job1 = {"name": "job1", "status": "running"}
        job2 = {"name": "job2", "status": "completed"}

        await file_registry.set("job1", job1)
        await file_registry.set("job2", job2)

        all_jobs = await file_registry.get_all()
        assert len(all_jobs) == 2
        assert all_jobs["job1"] == job1
        assert all_jobs["job2"] == job2


@pytest.mark.asyncio
class TestRegistryFactory:
    """Test suite for registry factory"""

    async def test_create_memory_registry(self):
        """Test creating memory registry from factory"""
        registry = RegistryFactory.create("memory")
        assert isinstance(registry, MemoryJobRegistry)

        await registry.set("test", {"data": "value"})
        result = await registry.get("test")
        assert result["data"] == "value"

        await cleanup_registry(registry)

    async def test_create_file_registry(self):
        """Test creating file registry from factory"""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            filepath = Path(f.name)

        try:
            registry = RegistryFactory.create("file", filepath=str(filepath))
            assert isinstance(registry, (FileRegistry, RegistryAdapter))

            await registry.set("test", {"data": "value"})
            result = await registry.get("test")
            assert result["data"] == "value"

            await cleanup_registry(registry)

        finally:
            if filepath.exists():
                filepath.unlink()
            lockfile = filepath.with_suffix(".lock")
            if lockfile.exists():
                lockfile.unlink()

    async def test_invalid_backend(self):
        """Test that invalid backend raises ValueError"""
        with pytest.raises(ValueError, match="Unsupported registry backend"):
            RegistryFactory.create("invalid_backend")


@pytest.mark.asyncio
class TestAdapterContract:
    """Test that all adapters follow the same contract"""

    @pytest.fixture(params=["memory", "file"])
    async def registry(self, request):
        """Parametrized fixture that yields different registry types"""
        if request.param == "memory":
            reg = MemoryJobRegistry()
        elif request.param == "file":
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                filepath = Path(f.name)
            reg = FileRegistry(filepath=filepath)

        yield reg

        await cleanup_registry(reg)

        # Clean up file registry artifacts
        if request.param == "file":
            if filepath.exists():
                filepath.unlink()
            lockfile = filepath.with_suffix(".lock")
            if lockfile.exists():
                lockfile.unlink()

    async def test_adapter_interface(self, registry):
        """Test that all adapters implement the full interface"""
        # Test basic operations
        await registry.set("job1", {"status": "running"})
        assert await registry.exists("job1")

        result = await registry.get("job1")
        assert result["status"] == "running"

        await registry.update("job1", {"status": "completed"})
        updated = await registry.get("job1")
        assert updated["status"] == "completed"

        all_jobs = await registry.get_all()
        assert "job1" in all_jobs

        deleted = await registry.delete("job1")
        assert deleted is True
        assert not await registry.exists("job1")
