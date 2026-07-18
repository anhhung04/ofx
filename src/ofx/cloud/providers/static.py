"""Static cloud provider for pre-existing VPS instances.

No provisioning or teardown — just wraps existing hosts for CloudJobRunner.
"""

from __future__ import annotations

import asyncio
import logging

from ofx.cloud.base import CloudProvider, CloudProviderRegistry
from ofx.cloud.models import CloudInstanceInfo
from ofx.models.cloud import CloudConfig

logger = logging.getLogger("ofx")

@CloudProviderRegistry.register("static")
class StaticProvider(CloudProvider):
    """Provider for pre-existing VPS instances.

    Used when you already have running VPS(es) and just want OFX to
    execute jobs on them without managing instance lifecycle.

    Supports single host (config.host) or multi-host fleet (config.hosts).
    """

    def __init__(self, **kwargs):
        """Static provider needs no credentials."""
        ...

    @staticmethod
    def _instance_id(host: str) -> str:
        return f"static-{host}"

    @classmethod
    def _instance_info(
        cls,
        host: str,
        *,
        name: str,
        metadata: dict | None = None,
    ) -> CloudInstanceInfo:
        return CloudInstanceInfo(
            instance_id=cls._instance_id(host),
            ip=host,
            status="active",
            provider="static",
            name=name,
            metadata=metadata or {},
        )

    @staticmethod
    def _resolved_static_host(config: CloudConfig) -> str:
        host = config.host
        if not host and config.hosts:
            return config.hosts[0].host
        return host

    @staticmethod
    def _fleet_host_metadata(host_entry: Any) -> dict[str, str]:
        return {
            "ssh_user": host_entry.ssh_user,
            "ssh_port": host_entry.ssh_port,
            "ssh_key": host_entry.ssh_key,
            "ssh_password": host_entry.ssh_password,
        }

    @classmethod
    def _fleet_instance_info(cls, host_entry: Any, index: int) -> CloudInstanceInfo:
        return cls._instance_info(
            host_entry.host,
            name=f"static-fleet-{index}-{host_entry.host}",
            metadata=cls._fleet_host_metadata(host_entry),
        )

    async def create_instance(self, config: CloudConfig) -> CloudInstanceInfo:
        """Return instance info for the static host. No actual provisioning."""
        host = self._resolved_static_host(config)

        if not host:
            raise ValueError(
                "Static provider requires 'host' or 'hosts' in cloud config"
            )

        return self._instance_info(host, name=f"static-{host}")

    async def create_fleet_instances(
        self, config: CloudConfig
    ) -> list[CloudInstanceInfo]:
        """Create instance info for all static hosts.

        Args:
            config: Cloud config with hosts list.

        Returns:
            List of CloudInstanceInfo for each host.
        """
        return [
            self._fleet_instance_info(host_entry, index)
            for index, host_entry in enumerate(config.hosts)
        ]

    async def wait_until_ready(
        self, instance_id: str, timeout: int = 300
    ) -> CloudInstanceInfo:
        """Verify the static host is reachable via SSH or WinRM.

        Polls with a simple connectivity check until timeout.
        """
        host = instance_id.removeprefix("static-")
        last_error = None

        async def _probe() -> bool:
            nonlocal last_error
            try:
                return await self._check_ssh_reachable(host)
            except Exception as exc:
                last_error = exc
                return False

        reachable = await self._poll_until(
            _probe,
            timeout=timeout,
            interval=5,
            is_ready=bool,
        )
        if reachable:
            return self._instance_info(host, name=instance_id)

        raise TimeoutError(
            f"Static host {host} not reachable after {timeout}s"
            + (f": {last_error}" if last_error else "")
        )

    async def _check_ssh_reachable(self, host: str, port: int = 22) -> bool:
        """Check if SSH port is open on host."""
        return await self._check_port_open(host, port, timeout=5)

    async def destroy_instance(self, instance_id: str) -> None:
        """No-op for static provider. Never destroy pre-existing instances."""
        logger.debug(f"Static provider: skipping destroy for {instance_id}")

    async def get_instance(self, instance_id: str) -> CloudInstanceInfo:
        """Return info for the static host."""
        host = instance_id.removeprefix("static-")
        return self._instance_info(host, name=instance_id)

    async def list_instances(
        self, tags: list[str] | None = None
    ) -> list[CloudInstanceInfo]:
        """Static provider doesn't track instances globally."""
        return []

    async def close(self) -> None:
        """No-op cleanup hook for static provider."""
        return None
