"""DigitalOcean cloud provider using pydo SDK.

Requires the optional 'pydo' package:
    pip install pydo
    # or: pip install ofx[digitalocean]
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from datetime import datetime

from ofx.cloud.base import CloudProvider, CloudProviderRegistry
from ofx.cloud.models import CloudInstanceInfo, SnapshotInfo
from ofx.models.cloud import CloudConfig
from ofx.settings import SECRETS_STORE
from ofx.utils.secrets import get_secret

logger = logging.getLogger("ofx")

try:
    from pydo import Client as DOClient  # type: ignore
except ImportError:
    DOClient = None


@CloudProviderRegistry.register("digitalocean")
class DigitalOceanProvider(CloudProvider):
    """DigitalOcean cloud provider via pydo SDK.

    Authentication:
        - token kwarg
        - DIGITALOCEAN_TOKEN env var
        - OFX secret: digitalocean_token

    Example:
        provider = CloudProviderRegistry.create("digitalocean", token="dop_v1_xxx")
        instance = await provider.create_instance(config)
    """

    def __init__(self, token: str = "", **kwargs):
        if DOClient is None:
            raise ImportError(
                "DigitalOcean support requires the 'pydo' package. "
                "Install with: pip install pydo  (or install with extras 'digitalocean')"
            )
        token_secret = get_secret("digitalocean_token", SECRETS_STORE)
        self._token = token or os.environ.get("DIGITALOCEAN_TOKEN", token_secret)
        if not self._token:
            raise ValueError(
                "DigitalOcean token required. Set DIGITALOCEAN_TOKEN env var or add a secret named 'digitalocean_token' to your OFX secrets store, "
                "and it will be automatically loaded."
            )
        self._client = DOClient(token=self._token)

    async def create_instance(self, config: CloudConfig) -> CloudInstanceInfo:
        """Create a DigitalOcean droplet.

        Args:
            config: Cloud config with region, size, image, ssh_key, tags.

        Returns:
            CloudInstanceInfo with the new droplet details.
        """
        # Resolve SSH key fingerprint/ID if provided
        ssh_keys = []
        if config.ssh_key:
            keys_resp = self._client.ssh_keys.list()
            for key in keys_resp.get("ssh_keys", []):
                ssh_keys.append(key["id"])

        droplet_name = f"ofx-{config.region}-{int(datetime.now().timestamp())}-{secrets.token_hex(3)}"
        tags = list(config.tags) if config.tags else []
        if "ofx" not in tags:
            tags.append("ofx")

        body = {
            "name": droplet_name,
            "region": config.region or "nyc3",
            "size": config.size or "s-1vcpu-1gb",
            "image": config.image,
            "ssh_keys": ssh_keys,
            "tags": tags,
            "backups": False,
            "ipv6": False,
            "monitoring": False,
        }

        if config.vpc_uuid:
            body["vpc_uuid"] = config.vpc_uuid
        if config.project_id:
            body["project_ids"] = [config.project_id]

        # If using password auth, enable user data for root password
        if config.ssh_password and not config.ssh_key:
            body["user_data"] = self._linux_password_userdata(config.ssh_password)

        resp = await asyncio.to_thread(self._client.droplets.create, body=body)
        droplet = resp.get("droplet", {})
        droplet_id = str(droplet.get("id", ""))

        return CloudInstanceInfo(
            instance_id=droplet_id,
            ip="",  # IP assigned after creation
            status=droplet.get("status", "new"),
            provider="digitalocean",
            region=config.region,
            size=config.size,
            image=config.image,
            name=droplet_name,
            tags=tags,
            metadata={"droplet": droplet},
        )

    async def wait_until_ready(
        self, instance_id: str, timeout: int = 300
    ) -> CloudInstanceInfo:
        """Wait for droplet to become active and have a public IP.

        Polls the DO API every 10 seconds until the droplet is active.
        """
        deadline = asyncio.get_running_loop().time() + timeout
        last_info = None

        while asyncio.get_running_loop().time() < deadline:
            info = await self.get_instance(instance_id)
            last_info = info

            if info.is_ready and info.ip:
                # Verify SSH is actually reachable
                if await self._check_ssh(info.ip):
                    logger.info(f"DO droplet '{info.name}' ready at {info.ip}")
                    return info

            await asyncio.sleep(10)

        ip = last_info.ip if last_info else "unknown"
        raise TimeoutError(
            f"DigitalOcean droplet {instance_id} ({ip}) not ready after {timeout}s"
        )

    async def _check_ssh(self, host: str, port: int = 22) -> bool:
        """Check if SSH port is open."""
        return await self._check_port_open(host, port, timeout=10)

    async def destroy_instance(self, instance_id: str) -> None:
        """Delete a DigitalOcean droplet."""
        await asyncio.to_thread(
            self._client.droplets.destroy, droplet_id=int(instance_id)
        )
        logger.info(f"Destroyed DO droplet with id {instance_id}")

    async def get_instance(self, instance_id: str) -> CloudInstanceInfo:
        """Get current droplet info."""
        resp = await asyncio.to_thread(
            self._client.droplets.get, droplet_id=int(instance_id)
        )
        droplet = resp.get("droplet", {})

        # Extract public IPv4
        ip = ""
        for network in droplet.get("networks", {}).get("v4", []):
            if network.get("type") == "public":
                ip = network.get("ip_address", "")
                break

        return CloudInstanceInfo(
            instance_id=instance_id,
            ip=ip,
            status=droplet.get("status", "unknown"),
            provider="digitalocean",
            region=droplet.get("region", {}).get("slug", ""),
            size=droplet.get("size_slug", ""),
            image=str(droplet.get("image", {}).get("slug", "")),
            name=droplet.get("name", ""),
            tags=droplet.get("tags", []),
        )

    async def list_instances(
        self, tags: list[str] | None = None
    ) -> list[CloudInstanceInfo]:
        """List droplets, optionally filtered by tag."""
        params = {}
        if tags:
            params["tag_name"] = tags[0]  # DO API supports single tag filter

        resp = await asyncio.to_thread(self._client.droplets.list, **params)
        instances = []
        for droplet in resp.get("droplets", []):
            ip = ""
            for network in droplet.get("networks", {}).get("v4", []):
                if network.get("type") == "public":
                    ip = network.get("ip_address", "")
                    break

            info = CloudInstanceInfo(
                instance_id=str(droplet["id"]),
                ip=ip,
                status=droplet.get("status", "unknown"),
                provider="digitalocean",
                region=droplet.get("region", {}).get("slug", ""),
                size=droplet.get("size_slug", ""),
                name=droplet.get("name", ""),
                tags=droplet.get("tags", []),
            )
            instances.append(info)

        return instances

    async def create_snapshot(self, instance_id: str, name: str) -> SnapshotInfo:
        """Create a snapshot from a droplet."""
        logger.info(f"Creating snapshot '{name}' from droplet {instance_id}")

        resp = await asyncio.to_thread(
            self._client.droplet_actions.post,
            droplet_id=int(instance_id),
            body={"type": "snapshot", "name": name},
        )
        action = resp.get("action", {})

        action_id = action.get("id")
        if action_id:
            await self._wait_for_action(action_id)

        # Find the snapshot in the droplet's snapshots
        snapshots = await self.list_snapshots()
        for snap in snapshots:
            if snap.name == name:
                return snap

        return SnapshotInfo(
            snapshot_id="pending",
            name=name,
            provider="digitalocean",
            status="in-progress",
        )

    async def _wait_for_action(self, action_id: int, timeout: int = 600) -> None:
        """Wait for a DO action to complete."""
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            resp = await asyncio.to_thread(
                self._client.actions.get, action_id=action_id
            )
            action = resp.get("action", {})
            if action.get("status") == "completed":
                return
            if action.get("status") == "errored":
                raise RuntimeError(f"DO action {action_id} failed")
            await asyncio.sleep(15)
        raise TimeoutError(f"DO action {action_id} timed out after {timeout}s")

    async def list_snapshots(self) -> list[SnapshotInfo]:
        """List available snapshots."""
        resp = await asyncio.to_thread(
            self._client.snapshots.list, resource_type="droplet"
        )
        snapshots = []
        for snap in resp.get("snapshots", []):
            snapshots.append(
                SnapshotInfo(
                    snapshot_id=str(snap["id"]),
                    name=snap.get("name", ""),
                    provider="digitalocean",
                    size_gb=snap.get("size_gigabytes", 0),
                    status="available",
                    created_at=snap.get("created_at"),
                    region=",".join(snap.get("regions", [])),
                )
            )
        return snapshots

    async def delete_snapshot(self, snapshot_id: str) -> None:
        """Delete a snapshot."""
        await asyncio.to_thread(self._client.snapshots.delete, snapshot_id=snapshot_id)

    async def close(self) -> None:
        """Clean up the pydo client."""
        if hasattr(self._client, "close"):
            self._client.close()
