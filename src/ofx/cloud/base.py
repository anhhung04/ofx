"""Abstract base class and registry for cloud providers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from ofx.cloud.models import CloudInstanceInfo, SnapshotInfo
from ofx.models.cloud import CloudConfig

logger = logging.getLogger("ofx")


class CloudProvider(ABC):
    """Abstract base class for all cloud providers.

    Subclasses implement instance lifecycle management for a specific
    cloud platform (DigitalOcean, AWS EC2, static hosts, etc.).

    Lifecycle:
        create_instance → wait_until_ready → [use instance] → destroy_instance
    """

    @abstractmethod
    async def create_instance(self, config: CloudConfig) -> CloudInstanceInfo:
        """Provision a new cloud instance.

        Args:
            config: Cloud configuration with provider-specific settings.

        Returns:
            Instance info with ID, IP (may be empty until ready), and status.
        """
        ...

    @abstractmethod
    async def wait_until_ready(
        self, instance_id: str, timeout: int = 300
    ) -> CloudInstanceInfo:
        """Wait for an instance to be fully ready (SSH/WinRM reachable).

        Args:
            instance_id: The instance ID from create_instance.
            timeout: Maximum seconds to wait.

        Returns:
            Updated instance info with IP and active status.

        Raises:
            TimeoutError: If instance doesn't become ready within timeout.
        """
        ...

    @abstractmethod
    async def destroy_instance(self, instance_id: str) -> None:
        """Destroy/terminate a cloud instance.

        Args:
            instance_id: The instance to destroy.
        """
        ...

    @abstractmethod
    async def get_instance(self, instance_id: str) -> CloudInstanceInfo:
        """Get current status of an instance.

        Args:
            instance_id: The instance to query.

        Returns:
            Current instance info.
        """
        ...

    async def list_instances(
        self, tags: list[str] | None = None
    ) -> list[CloudInstanceInfo]:
        """List instances, optionally filtered by tags.

        Args:
            tags: Filter by these tags. None returns all.

        Returns:
            List of matching instances.
        """
        return []

    async def create_snapshot(self, instance_id: str, name: str) -> SnapshotInfo:
        """Create a snapshot/image from a running instance.

        Args:
            instance_id: Instance to snapshot.
            name: Name for the snapshot.

        Returns:
            Snapshot info.

        Raises:
            NotImplementedError: If provider doesn't support snapshots.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support snapshot creation"
        )

    async def list_snapshots(self) -> list[SnapshotInfo]:
        """List available snapshots/images.

        Returns:
            List of snapshots.
        """
        return []

    async def delete_snapshot(self, snapshot_id: str) -> None:
        """Delete a snapshot/image.

        Args:
            snapshot_id: Snapshot to delete.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support snapshot deletion"
        )

    @abstractmethod
    async def close(self) -> None:
        """Clean up any resources (HTTP sessions, etc.)."""
        pass


class CloudProviderRegistry:
    """Registry for cloud provider implementations.

    Providers register via decorator:
        @CloudProviderRegistry.register("digitalocean")
        class DigitalOceanProvider(CloudProvider): ...

    Then create instances:
        provider = CloudProviderRegistry.create("digitalocean", token="...")
    """

    _providers: dict[str, type[CloudProvider]] = {}

    @classmethod
    def register(cls, name: str) -> Callable:
        """Decorator to register a cloud provider.

        Args:
            name: Provider name (e.g., "digitalocean", "aws", "static").

        Returns:
            Decorator function.
        """

        def decorator(provider_cls: type[CloudProvider]) -> type[CloudProvider]:
            cls._providers[name.lower()] = provider_cls
            logger.debug(f"Registered cloud provider: {name}")
            return provider_cls

        return decorator

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> CloudProvider:
        """Create a provider instance by name.

        Args:
            name: Provider name.
            **kwargs: Provider-specific constructor arguments.

        Returns:
            Configured provider instance.

        Raises:
            ValueError: If provider name is not registered.
        """
        name_lower = name.lower()
        if name_lower not in cls._providers:
            available = ", ".join(sorted(cls._providers.keys()))
            raise ValueError(f"Unknown cloud provider '{name}'. Available: {available}")
        return cls._providers[name_lower](**kwargs)

    @classmethod
    def list_providers(cls) -> list[str]:
        """List registered provider names."""
        return sorted(cls._providers.keys())

    @classmethod
    def get(cls, name: str) -> type[CloudProvider] | None:
        """Get a provider class by name without instantiation."""
        return cls._providers.get(name.lower())

    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove a provider from the registry."""
        cls._providers.pop(name.lower(), None)
