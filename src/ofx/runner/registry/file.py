"""File-based job registry adapter for persistent storage"""

import json
import logging
from pathlib import Path
from typing import Any

from filelock import FileLock

from ofx.runner.registry.base import RegistryAdapter
from ofx.settings import BASE_DATA_DIR, settings

logger = logging.getLogger(settings.app_branding)


class FileRegistry(RegistryAdapter):
    """File-based implementation of job registry

    Stores job data in a JSON file for persistence across process restarts.
    Uses file locking for concurrent access safety with an in-memory cache
    to reduce disk I/O for repeated reads.
    """

    def __init__(self, filepath: str | Path | None = None):
        """Initialize the file-based registry

        Args:
            filepath: Path to the JSON file for storing job data.
                     Defaults to ~/.ofx/job_registry.json
        """
        if filepath is None:
            filepath = BASE_DATA_DIR / "job_registry.json"

        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        # Create lock file alongside the data file
        self.lockfile = self.filepath.with_suffix(".lock")
        self._lock = FileLock(str(self.lockfile), timeout=10)

        # In-memory cache with mtime tracking
        self._cache: dict[str, Any] | None = None
        self._cache_mtime: float = 0.0

        # Initialize file if it doesn't exist
        if not self.filepath.exists():
            self.filepath.write_text("{}")

        self._log_debug(f"Initialized FileJobRegistry at {self.filepath}")

    def _read_cache_valid(self) -> bool:
        """Check if the in-memory cache is still valid (file not modified externally)."""
        if self._cache is None:
            return False
        try:
            current_mtime = self.filepath.stat().st_mtime
            return current_mtime == self._cache_mtime
        except OSError:
            return False

    async def _read_registry(self) -> dict[str, Any]:
        """Read the registry file with caching."""
        if self._read_cache_valid():
            return self._cache  # type: ignore[return-value]

        with self._lock:
            content = self.filepath.read_text()
            data = json.loads(content) if content.strip() else {}
            self._cache = data
            self._cache_mtime = self.filepath.stat().st_mtime
            return data

    async def _write_registry(self, data: dict[str, Any]) -> None:
        """Write data to the registry file and update cache."""
        with self._lock:
            self.filepath.write_text(json.dumps(data, default=str))
            self.filepath.chmod(0o600)
            self._cache = data
            self._cache_mtime = self.filepath.stat().st_mtime

    async def _set(self, key: str, value: Any) -> None:
        """Store data in file"""
        registry = await self._read_registry()
        registry[key] = value
        await self._write_registry(registry)
        self._log_debug(f"Set key '{key}' in FileJobRegistry")

    async def _get(self, key: str) -> Any | None:
        """Retrieve data from file"""
        registry = await self._read_registry()
        return registry.get(key)

    async def _update(self, key: str, updates: dict[str, Any]) -> None:
        """Update specific fields in data"""
        registry = await self._read_registry()
        existing = registry.get(key)
        if isinstance(existing, dict):
            existing.update(updates)
        else:
            registry[key] = updates
        await self._write_registry(registry)
        self._log_debug(f"Updated key '{key}' in FileJobRegistry")

    async def _delete(self, key: str) -> bool:
        """Remove data from file"""
        registry = await self._read_registry()
        if key in registry:
            del registry[key]
            await self._write_registry(registry)
            self._log_debug(f"Deleted key '{key}' from FileJobRegistry")
            return True
        return False

    async def _exists(self, key: str) -> bool:
        """Check if data exists in file"""
        registry = await self._read_registry()
        return key in registry

    async def _get_all(self) -> dict[str, Any]:
        """Get all entries from file"""
        return await self._read_registry()

    async def _clear(self) -> None:
        """Clear all entries from file"""
        await self._write_registry({})
        self._log_debug("Cleared FileJobRegistry")

    async def _close(self) -> None:
        """Close the registry and clean up resources"""
        self._cache = None
        self._cache_mtime = 0.0
        self._log_debug("Closed FileJobRegistry")

    @staticmethod
    def _log_debug(message: str) -> None:
        logger.debug(message)
