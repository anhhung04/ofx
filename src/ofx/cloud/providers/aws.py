"""AWS EC2 cloud provider using boto3.

Requires the optional 'boto3' package:
    pip install boto3
    # or: pip install ofx[aws]
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from ofx.cloud.base import CloudProvider, CloudProviderRegistry
from ofx.cloud.models import CloudInstanceInfo, SnapshotInfo
from ofx.models.cloud import CloudConfig

logger = logging.getLogger("ofx")

try:
    import boto3  # type: ignore
except ImportError:
    boto3 = None


@CloudProviderRegistry.register("aws")
class AWSProvider(CloudProvider):
    """AWS EC2 cloud provider via boto3.

    Authentication:
        - access_key_id + secret_access_key kwargs
        - AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY env vars
        - Default boto3 credential chain (~/.aws/credentials, IAM role, etc.)

    Example:
        provider = CloudProviderRegistry.create("aws", region="us-east-1")
        instance = await provider.create_instance(config)
    """

    def __init__(
        self,
        region: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
        **kwargs,
    ):
        if boto3 is None:
            raise ImportError(
                "AWS support requires the 'boto3' package. "
                "Install with: pip install boto3  (or: pip install ofx[aws])"
            )
        self._region = region or os.environ.get("AWS_DEFAULT_REGION", "") or "us-east-1"
        session_kwargs = {"region_name": self._region}
        if access_key_id:
            session_kwargs["aws_access_key_id"] = access_key_id
        if secret_access_key:
            session_kwargs["aws_secret_access_key"] = secret_access_key

        self._session = boto3.Session(**session_kwargs)
        self._ec2 = self._session.client("ec2")
        self._ec2_resource = self._session.resource("ec2")

    @staticmethod
    def _instance_name_tag(instance: dict) -> str:
        for tag in instance.get("Tags", []):
            if tag.get("Key", "") == "Name":
                return tag.get("Value", "")
        return ""

    @classmethod
    def _instance_info(cls, instance: dict) -> CloudInstanceInfo:
        return CloudInstanceInfo(
            instance_id=instance["InstanceId"],
            ip=instance.get("PublicIpAddress", ""),
            status=instance["State"]["Name"],
            provider="aws",
            region=instance.get("Placement", {}).get("AvailabilityZone", ""),
            size=instance.get("InstanceType", ""),
            image=instance.get("ImageId", ""),
            name=cls._instance_name_tag(instance),
        )

    @staticmethod
    def _list_instance_filters() -> list[dict[str, object]]:
        return [
            {"Name": "tag:ofx", "Values": ["true"]},
            {
                "Name": "instance-state-name",
                "Values": ["pending", "running", "stopping", "stopped"],
            },
        ]

    def _snapshot_info(self, image: dict) -> SnapshotInfo:
        return SnapshotInfo(
            snapshot_id=image["ImageId"],
            name=image.get("Name", ""),
            provider="aws",
            region=self._region,
            status=image.get("State", ""),
            created_at=image.get("CreationDate"),
        )

    @staticmethod
    def _snapshot_waiter_config() -> dict[str, int]:
        return {"Delay": 30, "MaxAttempts": 20}

    def _pending_snapshot_info(self, image_id: str, name: str) -> SnapshotInfo:
        return SnapshotInfo(
            snapshot_id=image_id,
            name=name,
            provider="aws",
            region=self._region,
            status="available",
        )

    def _new_instance_name(self, config: CloudConfig) -> str:
        return f"ofx-{config.region or self._region}-{int(datetime.now().timestamp())}"

    @staticmethod
    def _instance_tags(config: CloudConfig, instance_name: str) -> list[dict[str, str]]:
        tags = [{"Key": "Name", "Value": instance_name}, {"Key": "ofx", "Value": "true"}]
        for tag in config.tags:
            tags.append({"Key": tag, "Value": "true"})
        return tags

    def _instance_user_data(self, config: CloudConfig) -> str:
        if config.os == "windows" and config.winrm_password:
            return (
                "<powershell>\n"
                f'net user Administrator "{config.winrm_password}"\n'
                "winrm quickconfig -force\n"
                'winrm set winrm/config/service/auth @{Basic="true"}\n'
                'winrm set winrm/config/service @{AllowUnencrypted="true"}\n'
                'netsh advfirewall firewall add rule name="WinRM" '
                "dir=in action=allow protocol=TCP localport=5985\n"
                "</powershell>"
            )
        if config.os == "linux" and config.ssh_password and not config.ssh_key:
            return self._linux_password_userdata(config.ssh_password)
        return ""

    def _run_instances_kwargs(self, config: CloudConfig, instance_name: str) -> dict[str, Any]:
        run_kwargs: dict[str, Any] = {
            "ImageId": config.image,
            "InstanceType": config.size or "t3.micro",
            "MinCount": 1,
            "MaxCount": 1,
            "TagSpecifications": [
                {"ResourceType": "instance", "Tags": self._instance_tags(config, instance_name)},
            ],
        }

        if config.key_pair_name:
            run_kwargs["KeyName"] = config.key_pair_name
        if config.security_group:
            run_kwargs["SecurityGroupIds"] = [config.security_group]
        if config.subnet_id:
            run_kwargs["SubnetId"] = config.subnet_id
        if config.iam_instance_profile:
            run_kwargs["IamInstanceProfile"] = {"Name": config.iam_instance_profile}

        user_data = self._instance_user_data(config)
        if user_data:
            run_kwargs["UserData"] = user_data
        return run_kwargs

    @staticmethod
    def _waiter_config(timeout: int) -> dict[str, int]:
        return {"Delay": 10, "MaxAttempts": timeout // 10}

    def _waiter(self):
        return self._ec2.get_waiter("instance_running")

    async def _wait_for_running_state(self, instance_id: str, timeout: int) -> None:
        waiter = self._waiter()
        try:
            await asyncio.to_thread(
                waiter.wait,
                InstanceIds=[instance_id],
                WaiterConfig=self._waiter_config(timeout),
            )
        except Exception as exc:
            raise RuntimeError(
                f"Instance {instance_id} failed to reach running state: {exc}"
            ) from exc

    @staticmethod
    def _require_instance_ip(info: CloudInstanceInfo, instance_id: str) -> str:
        if info.ip:
            return info.ip
        raise RuntimeError(
            f"EC2 instance {instance_id} running but no public IP assigned. "
            "Check your VPC/subnet configuration."
        )

    async def _wait_for_instance_connectivity(
        self,
        instance_id: str,
        info: CloudInstanceInfo,
        timeout: int,
    ) -> CloudInstanceInfo:
        reachable = await self._poll_until(
            lambda: self._check_connectivity(info.ip),
            timeout=timeout,
            interval=5,
            is_ready=bool,
            limit=120,
        )
        if reachable:
            logger.info(f"EC2 instance {instance_id} ready at {info.ip}")
            return info

        logger.warning(
            f"EC2 instance {instance_id} running at {info.ip} but connectivity "
            "check timed out. It may still be booting."
        )
        return info

    async def create_instance(self, config: CloudConfig) -> CloudInstanceInfo:
        """Launch an EC2 instance.

        Args:
            config: Cloud config with region, size (instance type), image (AMI),
                    key_pair_name, security_group, subnet_id, tags.

        Returns:
            CloudInstanceInfo with the new instance details.
        """
        instance_name = self._new_instance_name(config)
        run_kwargs = self._run_instances_kwargs(config, instance_name)

        resp = await asyncio.to_thread(self._ec2.run_instances, **run_kwargs)

        instance = resp["Instances"][0]
        instance_id = instance["InstanceId"]

        return CloudInstanceInfo(
            instance_id=instance_id,
            ip="",  # Not assigned yet
            status=instance["State"]["Name"],
            provider="aws",
            region=config.region or self._region,
            size=config.size,
            image=config.image,
            name=instance_name,
            tags=config.tags,
            metadata={"instance": instance},
        )

    async def wait_until_ready(
        self, instance_id: str, timeout: int = 300
    ) -> CloudInstanceInfo:
        """Wait for EC2 instance to be running and have a public IP.

        Uses EC2 waiter then polls for SSH/WinRM reachability.
        """
        await self._wait_for_running_state(instance_id, timeout)
        info = await self.get_instance(instance_id)
        self._require_instance_ip(info, instance_id)
        return await self._wait_for_instance_connectivity(instance_id, info, timeout)

    async def _check_connectivity(self, host: str, port: int = 22) -> bool:
        """Check if SSH (22) or WinRM (5985) port is open."""
        for p in [port, 5985]:
            if await self._check_port_open(host, p, timeout=5):
                return True
        return False

    async def destroy_instance(self, instance_id: str) -> None:
        """Terminate an EC2 instance."""
        logger.info(f"Terminating EC2 instance {instance_id}")
        await asyncio.to_thread(
            self._ec2.terminate_instances, InstanceIds=[instance_id]
        )

    async def get_instance(self, instance_id: str) -> CloudInstanceInfo:
        """Get current EC2 instance info."""
        resp = await asyncio.to_thread(
            self._ec2.describe_instances, InstanceIds=[instance_id]
        )
        reservations = resp.get("Reservations", [])
        if not reservations or not reservations[0].get("Instances"):
            raise RuntimeError(f"Instance {instance_id} not found or has been terminated")

        instance = reservations[0]["Instances"][0]
        return self._instance_info(instance)

    async def list_instances(
        self, tags: list[str] | None = None
    ) -> list[CloudInstanceInfo]:
        """List EC2 instances, filtered by ofx tag."""
        resp = await asyncio.to_thread(
            self._ec2.describe_instances,
            Filters=self._list_instance_filters(),
        )

        instances = []
        for reservation in resp.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                instances.append(self._instance_info(instance))

        return instances

    async def create_snapshot(self, instance_id: str, name: str) -> SnapshotInfo:
        """Create an AMI from an EC2 instance."""
        logger.info(f"Creating AMI '{name}' from instance {instance_id}")

        resp = await asyncio.to_thread(
            self._ec2.create_image,
            InstanceId=instance_id,
            Name=name,
            Description=f"OFX snapshot from {instance_id}",
            NoReboot=False,
        )
        image_id = resp["ImageId"]

        waiter = self._ec2.get_waiter("image_available")
        try:
            await asyncio.to_thread(
                waiter.wait,
                ImageIds=[image_id],
                WaiterConfig=self._snapshot_waiter_config(),
            )
        except Exception:
            logger.warning(f"AMI {image_id} creation may still be in progress")

        return self._pending_snapshot_info(image_id, name)

    async def list_snapshots(self) -> list[SnapshotInfo]:
        """List AMIs owned by the account."""
        resp = await asyncio.to_thread(self._ec2.describe_images, Owners=["self"])
        return [self._snapshot_info(image) for image in resp.get("Images", [])]

    async def delete_snapshot(self, snapshot_id: str) -> None:
        """Deregister an AMI."""
        await asyncio.to_thread(self._ec2.deregister_image, ImageId=snapshot_id)

    async def close(self) -> None:
        """Clean up boto3 resources."""
        return None
