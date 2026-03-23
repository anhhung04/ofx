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
        pass

    async def create_instance(self, config: CloudConfig) -> CloudInstanceInfo:
        """Return instance info for the static host. No actual provisioning."""
        host = config.host
        if not host and config.hosts:
            # For fleet, caller should use create_fleet_instances() instead
            host = config.hosts[0].host

        if not host:
            raise ValueError(
                "Static provider requires 'host' or 'hosts' in cloud config"
            )

        return CloudInstanceInfo(
            instance_id=f"static-{host}",
            ip=host,
            status="active",
            provider="static",
            name=f"static-{host}",
        )

    async def create_fleet_instances(
        self, config: CloudConfig
    ) -> list[CloudInstanceInfo]:
        """Create instance info for all static hosts.

        Args:
            config: Cloud config with hosts list.

        Returns:
            List of CloudInstanceInfo for each host.
        """
        instances = []
        for i, host_entry in enumerate(config.hosts):
            instances.append(
                CloudInstanceInfo(
                    instance_id=f"static-{host_entry.host}",
                    ip=host_entry.host,
                    status="active",
                    provider="static",
                    name=f"static-fleet-{i}-{host_entry.host}",
                    metadata={
                        "ssh_user": host_entry.ssh_user,
                        "ssh_port": host_entry.ssh_port,
                        "ssh_key": host_entry.ssh_key,
                        "ssh_password": host_entry.ssh_password,
                    },
                )
            )
        return instances

    async def wait_until_ready(
        self, instance_id: str, timeout: int = 300
    ) -> CloudInstanceInfo:
        """Verify the static host is reachable via SSH or WinRM.

        Polls with a simple connectivity check until timeout.
        """
        host = instance_id.removeprefix("static-")
        deadline = asyncio.get_running_loop().time() + timeout
        last_error = None

        while asyncio.get_running_loop().time() < deadline:
            try:
                reachable = await self._check_ssh_reachable(host)
                if reachable:
                    return CloudInstanceInfo(
                        instance_id=instance_id,
                        ip=host,
                        status="active",
                        provider="static",
                    )
            except Exception as e:
                last_error = e

            await asyncio.sleep(5)

        raise TimeoutError(
            f"Static host {host} not reachable after {timeout}s"
            + (f": {last_error}" if last_error else "")
        )

    async def _check_ssh_reachable(self, host: str, port: int = 22) -> bool:
        """Check if SSH port is open on host."""
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=5
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (TimeoutError, OSError):
            return False

    async def destroy_instance(self, instance_id: str) -> None:
        """No-op for static provider. Never destroy pre-existing instances."""
        logger.debug(f"Static provider: skipping destroy for {instance_id}")

    async def get_instance(self, instance_id: str) -> CloudInstanceInfo:
        """Return info for the static host."""
        host = instance_id.removeprefix("static-")
        return CloudInstanceInfo(
            instance_id=instance_id,
            ip=host,
            status="active",
            provider="static",
        )

    async def list_instances(
        self, tags: list[str] | None = None
    ) -> list[CloudInstanceInfo]:
        """Static provider doesn't track instances globally."""
        return []

    async def close(self) -> None:
        """No-op cleanup hook for static provider."""
        return None
