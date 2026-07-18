"""Abstract base class and registry for cloud providers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
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
        raise self._unsupported_operation("snapshot creation")

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
        raise self._unsupported_operation("snapshot deletion")

    @abstractmethod
    async def close(self) -> None:
        """Clean up any resources (HTTP sessions, etc.)."""
        ...

    def _unsupported_operation(self, operation: str) -> NotImplementedError:
        return NotImplementedError(
            f"{self.__class__.__name__} does not support {operation}"
        )

    @staticmethod
    async def _check_port_open(host: str, port: int = 22, timeout: float = 5) -> bool:
        """Check whether a TCP port is reachable.

        Shared connectivity probe used by all providers during
        ``wait_until_ready`` polling.
        """
        import asyncio as _aio

        try:
            _, writer = await _aio.wait_for(
                _aio.open_connection(host, port), timeout=timeout
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (TimeoutError, OSError):
            return False

    @staticmethod
    def _linux_password_userdata(password: str) -> str:
        """Generate cloud-init user data to enable root password auth on Linux."""
        return (
            "#!/bin/bash\n"
            f'echo "root:{password}" | chpasswd\n'
            'sed -i "s/.*PasswordAuthentication.*/PasswordAuthentication yes/" '
            "/etc/ssh/sshd_config\n"
            'sed -i "s/.*PermitRootLogin.*/PermitRootLogin yes/" '
            "/etc/ssh/sshd_config\n"
            "systemctl restart sshd\n"
        )

    @staticmethod
    def _poll_deadline(timeout: int, *, limit: int | None = None) -> float:
        duration = min(timeout, limit) if limit is not None else timeout
        return __import__("asyncio").get_running_loop().time() + duration

    @staticmethod
    async def _poll_until(
        probe: Callable[[], Awaitable[Any]],
        *,
        timeout: int,
        interval: float,
        is_ready: Callable[[Any], bool],
        limit: int | None = None,
    ) -> Any:
        import asyncio as _aio

        deadline = CloudProvider._poll_deadline(timeout, limit=limit)
        last_result: Any = None
        while _aio.get_running_loop().time() < deadline:
            last_result = await probe()
            if is_ready(last_result):
                return last_result
            await _aio.sleep(interval)
        return last_result

class CloudProviderRegistry:
    """Registry for cloud provider implementations.

    Providers register via decorator:
        @CloudProviderRegistry.register("digitalocean")
        class DigitalOceanProvider(CloudProvider): ...

    Then create instances:
        provider = CloudProviderRegistry.create("digitalocean", token="...")
    """

    _providers: dict[str, type[CloudProvider]] = {}

    @staticmethod
    def _normalized_name(name: str) -> str:
        return name.lower()

    @classmethod
    def _available_provider_names(cls) -> str:
        return ", ".join(sorted(cls._providers.keys()))

    @classmethod
    def _provider_class(cls, name: str) -> type[CloudProvider] | None:
        return cls._providers.get(cls._normalized_name(name))

    @classmethod
    def register(cls, name: str) -> Callable:
        """Decorator to register a cloud provider.

        Args:
            name: Provider name (e.g., "digitalocean", "aws", "static").

        Returns:
            Decorator function.
        """

        def decorator(provider_cls: type[CloudProvider]) -> type[CloudProvider]:
            cls._providers[cls._normalized_name(name)] = provider_cls
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
        provider_cls = cls._provider_class(name)
        if provider_cls is None:
            available = cls._available_provider_names()
            raise ValueError(f"Unknown cloud provider '{name}'. Available: {available}")
        return provider_cls(**kwargs)

    @classmethod
    def list_providers(cls) -> list[str]:
        """List registered provider names."""
        return sorted(cls._providers.keys())

    @classmethod
    def get(cls, name: str) -> type[CloudProvider] | None:
        """Get a provider class by name without instantiation."""
        return cls._provider_class(name)

    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove a provider from the registry."""
        cls._providers.pop(cls._normalized_name(name), None)
