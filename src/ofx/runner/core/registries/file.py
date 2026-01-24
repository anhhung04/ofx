"""File-based job registry adapter for persistent storage"""

import json
import logging
from pathlib import Path
from typing import Any

import aiofiles
from filelock import FileLock

from ofx.runner.core.registries.base import RegistryAdapter
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class FileJobRegistry(RegistryAdapter):
    """File-based implementation of job registry

    Stores job data in a JSON file for persistence across process restarts.
    Uses file locking for concurrent access safety.
    """

    def __init__(self, filepath: str | Path | None = None):
        """Initialize the file-based registry

        Args:
            filepath: Path to the JSON file for storing job data.
                     Defaults to ~/.local/share/ofx/job_registry.json
        """
        if filepath is None:
            filepath = Path.home() / ".local" / "share" / "ofx" / "job_registry.json"

        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        # Create lock file alongside the data file
        self.lockfile = self.filepath.with_suffix(".lock")
        self._lock = FileLock(str(self.lockfile), timeout=10)

        # Initialize file if it doesn't exist
        if not self.filepath.exists():
            self.filepath.write_text("{}")

        logger.debug(f"Initialized FileJobRegistry at {self.filepath}")

    async def _read_registry(self) -> dict[str, dict[str, Any]]:
        """Read the registry file

        Returns:
            Dictionary of registry data
        """
        async with aiofiles.open(self.filepath) as f:
            content = await f.read()
            return json.loads(content) if content else {}

    async def _write_registry(self, data: dict[str, dict[str, Any]]) -> None:
        """Write data to the registry file

        Args:
            data: Dictionary of registry data to write
        """
        async with aiofiles.open(self.filepath, "w") as f:
            await f.write(json.dumps(data, indent=2))

    async def set(self, key: str, value: dict[str, Any]) -> None:
        """Store data in file

        Args:
            key: Unique identifier for the data
            value: Data to store (must be JSON-serializable)
        """
        with self._lock:
            registry = await self._read_registry()
            registry[key] = value
            await self._write_registry(registry)
            logger.debug(f"Set key '{key}' in FileJobRegistry")

    async def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve data from file

        Args:
            key: Unique identifier for the data

        Returns:
            Data if found, None otherwise
        """
        with self._lock:
            registry = await self._read_registry()
            return registry.get(key)

    async def update(self, key: str, updates: dict[str, Any]) -> None:
        """Update specific fields in data

        Args:
            key: Unique identifier for the data
            updates: Fields to update in the data
        """
        with self._lock:
            registry = await self._read_registry()
            if key in registry:
                registry[key].update(updates)
                await self._write_registry(registry)
                logger.debug(f"Updated key '{key}' in FileJobRegistry")
            else:
                logger.warning(
                    f"Cannot update key '{key}' - not found in FileJobRegistry"
                )

    async def delete(self, key: str) -> bool:
        """Remove data from file

        Args:
            key: Unique identifier for the data

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            registry = await self._read_registry()
            if key in registry:
                del registry[key]
                await self._write_registry(registry)
                logger.debug(f"Deleted key '{key}' from FileJobRegistry")
                return True
            return False

    async def exists(self, key: str) -> bool:
        """Check if data exists in file

        Args:
            key: Unique identifier for the data

        Returns:
            True if data exists, False otherwise
        """
        with self._lock:
            registry = await self._read_registry()
            return key in registry

    async def get_all(self) -> dict[str, dict[str, Any]]:
        """Get all entries from file

        Returns:
            Dictionary mapping keys to their data
        """
        with self._lock:
            return await self._read_registry()

    async def clear(self) -> None:
        """Clear all entries from file"""
        with self._lock:
            await self._write_registry({})
            logger.debug("Cleared FileJobRegistry")

    async def close(self) -> None:
        """Close the registry and clean up resources"""
        logger.debug("Closed FileJobRegistry")
