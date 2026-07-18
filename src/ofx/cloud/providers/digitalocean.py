"""DigitalOcean cloud provider using pydo SDK.

Requires the optional 'pydo' package:
    pip install pydo
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
    from pydo import Client as DOClient
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

    @staticmethod
    def _public_ipv4(droplet: dict) -> str:
        for network in droplet.get("networks", {}).get("v4", []):
            if network.get("type") == "public":
                return network.get("ip_address", "")
        return ""

    @classmethod
    def _droplet_info(cls, droplet: dict) -> CloudInstanceInfo:
        return CloudInstanceInfo(
            instance_id=str(droplet.get("id", "")),
            ip=cls._public_ipv4(droplet),
            status=droplet.get("status", "unknown"),
            provider="digitalocean",
            region=droplet.get("region", {}).get("slug", ""),
            size=droplet.get("size_slug", ""),
            image=str(droplet.get("image", {}).get("slug", "")),
            name=droplet.get("name", ""),
            tags=droplet.get("tags", []),
        )

    @staticmethod
    def _resolve_ssh_key_ids(available_keys: list[dict], ssh_key: str) -> list[int]:
        ssh_key_ids: list[int] = []
        for key in available_keys:
            if key.get("name") == ssh_key or key.get("fingerprint") == ssh_key:
                ssh_key_ids.append(key["id"])
        return ssh_key_ids

    def _droplet_ssh_keys(self, config: CloudConfig) -> list[int]:
        if not config.ssh_key:
            return []

        keys_resp = self._client.ssh_keys.list()
        available_keys = keys_resp.get("ssh_keys", [])
        ssh_key_ids = self._resolve_ssh_key_ids(available_keys, config.ssh_key)
        if not ssh_key_ids:
            raise RuntimeError(
                f"SSH key '{config.ssh_key}' not found in DigitalOcean account. "
                f"Available keys: {[k.get('name') for k in available_keys]}"
            )
        return ssh_key_ids

    @staticmethod
    def _droplet_name(config: CloudConfig) -> str:
        return f"ofx-{config.region}-{int(datetime.now().timestamp())}-{secrets.token_hex(3)}"

    @staticmethod
    def _droplet_tags(config: CloudConfig) -> list[str]:
        tags = list(config.tags) if config.tags else []
        if "ofx" not in tags:
            tags.append("ofx")
        return tags

    def _droplet_create_body(self, config: CloudConfig) -> dict[str, object]:
        body: dict[str, object] = {
            "name": self._droplet_name(config),
            "region": config.region or "nyc3",
            "size": config.size or "s-1vcpu-1gb",
            "image": config.image,
            "ssh_keys": self._droplet_ssh_keys(config),
            "tags": self._droplet_tags(config),
            "backups": False,
            "ipv6": False,
            "monitoring": False,
        }

        if config.vpc_uuid:
            body["vpc_uuid"] = config.vpc_uuid
        if config.project_id:
            body["project_ids"] = [config.project_id]
        if config.ssh_password and not config.ssh_key:
            body["user_data"] = self._linux_password_userdata(config.ssh_password)
        return body

    @staticmethod
    def _droplet_create_result(
        config: CloudConfig,
        *,
        droplet: dict,
        droplet_name: str,
        tags: list[str],
    ) -> CloudInstanceInfo:
        return CloudInstanceInfo(
            instance_id=str(droplet["id"]),
            ip="",
            status=droplet.get("status", "new"),
            provider="digitalocean",
            region=config.region,
            size=config.size,
            image=config.image,
            name=droplet_name,
            tags=tags,
            metadata={"droplet": droplet},
        )

    @staticmethod
    def _action_status(action: dict) -> str:
        return action.get("status", "")

    @staticmethod
    def _snapshot_info(snapshot: dict) -> SnapshotInfo:
        return SnapshotInfo(
            snapshot_id=str(snapshot["id"]),
            name=snapshot.get("name", ""),
            provider="digitalocean",
            size_gb=snapshot.get("size_gigabytes", 0),
            status="available",
            created_at=snapshot.get("created_at"),
            region=",".join(snapshot.get("regions", [])),
        )

    @staticmethod
    def _pending_snapshot_info(name: str) -> SnapshotInfo:
        return SnapshotInfo(
            snapshot_id="pending",
            name=name,
            provider="digitalocean",
            status="in-progress",
        )

    @staticmethod
    def _snapshot_named(snapshots: list[SnapshotInfo], name: str) -> SnapshotInfo | None:
        for snapshot in snapshots:
            if snapshot.name == name:
                return snapshot
        return None

    @staticmethod
    def _require_non_error_status(instance_id: str, info: CloudInstanceInfo) -> None:
        if info.status == "errored":
            raise RuntimeError(
                f"DigitalOcean droplet {instance_id} entered error state during provisioning"
            )

    @staticmethod
    def _droplet_timeout_error(
        instance_id: str,
        timeout: int,
        last_info: CloudInstanceInfo | None,
    ) -> TimeoutError:
        ip = last_info.ip if last_info else "unknown"
        return TimeoutError(
            f"DigitalOcean droplet {instance_id} ({ip}) not ready after {timeout}s"
        )

    async def _wait_for_ready_droplet(
        self,
        instance_id: str,
        timeout: int,
    ) -> CloudInstanceInfo:
        last_info: CloudInstanceInfo | None = None

        async def _probe() -> tuple[CloudInstanceInfo, bool]:
            nonlocal last_info
            info = await self.get_instance(instance_id)
            last_info = info
            self._require_non_error_status(instance_id, info)
            ssh_ready = bool(info.is_ready and info.ip and await self._check_ssh(info.ip))
            return info, ssh_ready

        result = await self._poll_until(
            _probe,
            timeout=timeout,
            interval=10,
            is_ready=lambda current: current[1],
        )
        if result is not None:
            info, ssh_ready = result
            if ssh_ready:
                logger.info(f"DO droplet '{info.name}' ready at {info.ip}")
                return info

        raise self._droplet_timeout_error(instance_id, timeout, last_info)

    async def create_instance(self, config: CloudConfig) -> CloudInstanceInfo:
        """Create a DigitalOcean droplet.

        Args:
            config: Cloud config with region, size, image, ssh_key, tags.

        Returns:
            CloudInstanceInfo with the new droplet details.
        """
        body = self._droplet_create_body(config)
        droplet_name = body["name"]
        tags = body["tags"]

        resp = await asyncio.to_thread(self._client.droplets.create, body=body)
        droplet = resp.get("droplet", {})
        droplet_id = droplet.get("id")
        if not droplet_id:
            raise RuntimeError(
                f"DigitalOcean droplet creation failed: no droplet ID in response. "
                f"Response: {resp}"
            )
        return self._droplet_create_result(
            config,
            droplet=droplet,
            droplet_name=str(droplet_name),
            tags=list(tags),
        )

    async def wait_until_ready(
        self, instance_id: str, timeout: int = 300
    ) -> CloudInstanceInfo:
        """Wait for droplet to become active and have a public IP.

        Polls the DO API every 10 seconds until the droplet is active.
        """
        return await self._wait_for_ready_droplet(instance_id, timeout)

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
        return self._droplet_info(droplet)

    async def list_instances(
        self, tags: list[str] | None = None
    ) -> list[CloudInstanceInfo]:
        """List droplets, optionally filtered by tag."""
        params = {}
        if tags:
            params["tag_name"] = tags[0]

        resp = await asyncio.to_thread(self._client.droplets.list, **params)
        instances = []
        for droplet in resp.get("droplets", []):
            instances.append(self._droplet_info(droplet))

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

        snapshots = await self.list_snapshots()
        snapshot = self._snapshot_named(snapshots, name)
        if snapshot is not None:
            return snapshot

        return self._pending_snapshot_info(name)

    async def _wait_for_action(self, action_id: int, timeout: int = 600) -> None:
        """Wait for a DO action to complete."""
        action = await self._poll_until(
            lambda: self._fetch_action(action_id),
            timeout=timeout,
            interval=15,
            is_ready=lambda current: self._action_status(current) == "completed",
        )
        status = self._action_status(action or {})
        if status == "completed":
            return
        if status == "errored":
            raise RuntimeError(f"DO action {action_id} failed")
        raise TimeoutError(f"DO action {action_id} timed out after {timeout}s")

    async def _fetch_action(self, action_id: int) -> dict:
        resp = await asyncio.to_thread(self._client.actions.get, action_id=action_id)
        return resp.get("action", {})

    async def list_snapshots(self) -> list[SnapshotInfo]:
        """List available snapshots."""
        resp = await asyncio.to_thread(
            self._client.snapshots.list, resource_type="droplet"
        )
        return [self._snapshot_info(snapshot) for snapshot in resp.get("snapshots", [])]

    async def delete_snapshot(self, snapshot_id: str) -> None:
        """Delete a snapshot."""
        await asyncio.to_thread(self._client.snapshots.delete, snapshot_id=snapshot_id)

    async def close(self) -> None:
        """Clean up the pydo client."""
        if hasattr(self._client, "close"):
            self._client.close()
