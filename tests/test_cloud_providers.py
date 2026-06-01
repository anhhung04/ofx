"""Tests for AWS and DigitalOcean cloud provider implementations.

Uses unittest.mock to simulate boto3/pydo SDK responses without real API calls.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from ofx.models.cloud import CloudConfig

# ─── AWS Provider Tests ────────────────────────────────────────────


def _make_aws_provider():
    """Create an AWSProvider with mocked boto3 session."""
    mock_session = MagicMock()
    mock_ec2_client = MagicMock()
    mock_ec2_resource = MagicMock()
    mock_session.client.return_value = mock_ec2_client
    mock_session.resource.return_value = mock_ec2_resource

    with patch("ofx.cloud.providers.aws.boto3") as mock_boto3:
        mock_boto3.Session.return_value = mock_session
        from ofx.cloud.providers.aws import AWSProvider

        provider = AWSProvider(region="us-east-1")
    return provider, mock_ec2_client


def _make_cloud_config(**overrides) -> CloudConfig:
    defaults = {
        "provider": "aws",
        "region": "us-east-1",
        "size": "t3.micro",
        "image": "ami-12345678",
    }
    defaults.update(overrides)
    return CloudConfig(**defaults)


class TestAWSCreateInstance:
    def test_run_instances_kwargs_builds_optional_fields(self):
        provider, _ec2 = _make_aws_provider()
        config = _make_cloud_config(
            key_pair_name="my-key",
            security_group="sg-12345",
            subnet_id="subnet-abc",
            iam_instance_profile="my-profile",
            tags=["scan", "recon"],
        )

        kwargs = provider._run_instances_kwargs(config, "ofx-us-east-1-123")

        assert kwargs["KeyName"] == "my-key"
        assert kwargs["SecurityGroupIds"] == ["sg-12345"]
        assert kwargs["SubnetId"] == "subnet-abc"
        assert kwargs["IamInstanceProfile"] == {"Name": "my-profile"}
        tags = kwargs["TagSpecifications"][0]["Tags"]
        tag_keys = [tag["Key"] for tag in tags]
        assert "Name" in tag_keys
        assert "ofx" in tag_keys
        assert "scan" in tag_keys
        assert "recon" in tag_keys

    def test_instance_user_data_windows_and_linux(self):
        provider, _ec2 = _make_aws_provider()

        windows_data = provider._instance_user_data(
            _make_cloud_config(os="windows", winrm_password="P@ssw0rd")
        )
        linux_data = provider._instance_user_data(
            _make_cloud_config(os="linux", ssh_password="rootpass")
        )

        assert "winrm quickconfig" in windows_data
        assert "P@ssw0rd" in windows_data
        assert "chpasswd" in linux_data
        assert "rootpass" in linux_data

    def test_basic_launch(self):
        provider, ec2 = _make_aws_provider()
        ec2.run_instances.return_value = {
            "Instances": [
                {
                    "InstanceId": "i-abc123",
                    "State": {"Name": "pending"},
                }
            ]
        }

        config = _make_cloud_config()
        info = asyncio.run(provider.create_instance(config))

        assert info.instance_id == "i-abc123"
        assert info.provider == "aws"
        assert info.status == "pending"
        assert info.ip == ""
        ec2.run_instances.assert_called_once()

        call_kwargs = ec2.run_instances.call_args[1]
        assert call_kwargs["ImageId"] == "ami-12345678"
        assert call_kwargs["InstanceType"] == "t3.micro"

    def test_launch_with_key_pair_and_security_group(self):
        provider, ec2 = _make_aws_provider()
        ec2.run_instances.return_value = {
            "Instances": [{"InstanceId": "i-def456", "State": {"Name": "pending"}}]
        }

        config = _make_cloud_config(key_pair_name="my-key", security_group="sg-12345")
        asyncio.run(provider.create_instance(config))

        call_kwargs = ec2.run_instances.call_args[1]
        assert call_kwargs["KeyName"] == "my-key"
        assert call_kwargs["SecurityGroupIds"] == ["sg-12345"]

    def test_launch_with_subnet_and_iam(self):
        provider, ec2 = _make_aws_provider()
        ec2.run_instances.return_value = {
            "Instances": [{"InstanceId": "i-sub123", "State": {"Name": "pending"}}]
        }

        config = _make_cloud_config(
            subnet_id="subnet-abc", iam_instance_profile="my-profile"
        )
        asyncio.run(provider.create_instance(config))

        call_kwargs = ec2.run_instances.call_args[1]
        assert call_kwargs["SubnetId"] == "subnet-abc"
        assert call_kwargs["IamInstanceProfile"] == {"Name": "my-profile"}

    def test_launch_with_tags(self):
        provider, ec2 = _make_aws_provider()
        ec2.run_instances.return_value = {
            "Instances": [{"InstanceId": "i-tag123", "State": {"Name": "pending"}}]
        }

        config = _make_cloud_config(tags=["scan", "recon"])
        info = asyncio.run(provider.create_instance(config))

        tags = ec2.run_instances.call_args[1]["TagSpecifications"][0]["Tags"]
        tag_keys = [t["Key"] for t in tags]
        assert "Name" in tag_keys
        assert "ofx" in tag_keys
        assert "scan" in tag_keys
        assert "recon" in tag_keys
        assert info.tags == ["scan", "recon"]

    def test_launch_windows_with_winrm_user_data(self):
        provider, ec2 = _make_aws_provider()
        ec2.run_instances.return_value = {
            "Instances": [{"InstanceId": "i-win123", "State": {"Name": "pending"}}]
        }

        config = _make_cloud_config(os="windows", winrm_password="P@ssw0rd")
        asyncio.run(provider.create_instance(config))

        user_data = ec2.run_instances.call_args[1]["UserData"]
        assert "<powershell>" in user_data
        assert "P@ssw0rd" in user_data
        assert "winrm quickconfig" in user_data

    def test_launch_linux_with_password_user_data(self):
        provider, ec2 = _make_aws_provider()
        ec2.run_instances.return_value = {
            "Instances": [{"InstanceId": "i-lin123", "State": {"Name": "pending"}}]
        }

        config = _make_cloud_config(os="linux", ssh_password="rootpass")
        asyncio.run(provider.create_instance(config))

        user_data = ec2.run_instances.call_args[1]["UserData"]
        assert "chpasswd" in user_data
        assert "rootpass" in user_data
        assert "PasswordAuthentication yes" in user_data


class TestAWSGetInstance:
    def test_instance_info_helper_extracts_fields(self):
        provider, _ec2 = _make_aws_provider()
        instance = {
            "InstanceId": "i-abc123",
            "PublicIpAddress": "1.2.3.4",
            "State": {"Name": "running"},
            "Placement": {"AvailabilityZone": "us-east-1a"},
            "InstanceType": "t3.micro",
            "ImageId": "ami-12345678",
            "Tags": [{"Key": "Name", "Value": "ofx-test"}],
        }

        info = provider._instance_info(instance)

        assert info.instance_id == "i-abc123"
        assert info.ip == "1.2.3.4"
        assert info.name == "ofx-test"

    def test_waiter_config_and_deadline_helpers(self):
        provider, _ec2 = _make_aws_provider()
        assert provider._waiter_config(300) == {"Delay": 10, "MaxAttempts": 30}

    def test_snapshot_helpers(self):
        provider, _ec2 = _make_aws_provider()
        image = {
            "ImageId": "ami-001",
            "Name": "snap-a",
            "State": "available",
            "CreationDate": "2024-01-01T00:00:00Z",
        }

        snapshot = provider._snapshot_info(image)

        assert snapshot.snapshot_id == "ami-001"
        assert snapshot.name == "snap-a"
        assert provider._snapshot_waiter_config() == {"Delay": 30, "MaxAttempts": 20}

    def test_require_instance_ip_raises_without_ip(self):
        provider, _ec2 = _make_aws_provider()
        with pytest.raises(RuntimeError, match="no public IP assigned"):
            provider._require_instance_ip(
                provider._instance_info(
                    {
                        "InstanceId": "i-noip",
                        "State": {"Name": "running"},
                        "Tags": [],
                    }
                ),
                "i-noip",
            )

    def test_get_instance_with_ip(self):
        provider, ec2 = _make_aws_provider()
        ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-abc123",
                            "PublicIpAddress": "1.2.3.4",
                            "State": {"Name": "running"},
                            "Placement": {"AvailabilityZone": "us-east-1a"},
                            "InstanceType": "t3.micro",
                            "ImageId": "ami-12345678",
                            "Tags": [{"Key": "Name", "Value": "ofx-test"}],
                        }
                    ]
                }
            ]
        }

        info = asyncio.run(provider.get_instance("i-abc123"))
        assert info.ip == "1.2.3.4"
        assert info.status == "running"
        assert info.name == "ofx-test"
        assert info.region == "us-east-1a"

    def test_get_instance_not_found(self):
        provider, ec2 = _make_aws_provider()
        ec2.describe_instances.return_value = {"Reservations": []}

        with pytest.raises(RuntimeError, match="not found"):
            asyncio.run(provider.get_instance("i-nonexistent"))

    def test_get_instance_no_ip(self):
        provider, ec2 = _make_aws_provider()
        ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-noip",
                            "State": {"Name": "running"},
                            "Tags": [],
                        }
                    ]
                }
            ]
        }

        info = asyncio.run(provider.get_instance("i-noip"))
        assert info.ip == ""
        assert info.name == ""


class TestAWSDestroyInstance:
    def test_destroy(self):
        provider, ec2 = _make_aws_provider()
        ec2.terminate_instances.return_value = {}

        asyncio.run(provider.destroy_instance("i-abc123"))
        ec2.terminate_instances.assert_called_once_with(InstanceIds=["i-abc123"])


class TestAWSListInstances:
    def test_list_instances(self):
        provider, ec2 = _make_aws_provider()
        ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-aaa",
                            "PublicIpAddress": "10.0.0.1",
                            "State": {"Name": "running"},
                            "Tags": [{"Key": "Name", "Value": "ofx-1"}],
                            "Placement": {"AvailabilityZone": "us-east-1a"},
                            "InstanceType": "t3.micro",
                            "ImageId": "ami-111",
                        },
                        {
                            "InstanceId": "i-bbb",
                            "State": {"Name": "stopped"},
                            "Tags": [],
                        },
                    ]
                }
            ]
        }

        instances = asyncio.run(provider.list_instances())
        assert len(instances) == 2
        assert instances[0].instance_id == "i-aaa"
        assert instances[0].ip == "10.0.0.1"
        assert instances[1].instance_id == "i-bbb"
        assert instances[1].ip == ""

    def test_list_empty(self):
        provider, ec2 = _make_aws_provider()
        ec2.describe_instances.return_value = {"Reservations": []}

        instances = asyncio.run(provider.list_instances())
        assert instances == []


class TestAWSSnapshots:
    def test_create_snapshot(self):
        provider, ec2 = _make_aws_provider()
        ec2.create_image.return_value = {"ImageId": "ami-snap123"}
        waiter = MagicMock()
        ec2.get_waiter.return_value = waiter

        snap = asyncio.run(provider.create_snapshot("i-abc123", "my-snap"))
        assert snap.snapshot_id == "ami-snap123"
        assert snap.name == "my-snap"
        assert snap.provider == "aws"

    def test_list_snapshots(self):
        provider, ec2 = _make_aws_provider()
        ec2.describe_images.return_value = {
            "Images": [
                {
                    "ImageId": "ami-001",
                    "Name": "snap-a",
                    "State": "available",
                    "CreationDate": "2024-01-01T00:00:00Z",
                },
                {"ImageId": "ami-002", "Name": "snap-b", "State": "available"},
            ]
        }

        snaps = asyncio.run(provider.list_snapshots())
        assert len(snaps) == 2
        assert snaps[0].snapshot_id == "ami-001"
        assert snaps[1].name == "snap-b"

    def test_delete_snapshot(self):
        provider, ec2 = _make_aws_provider()
        ec2.deregister_image.return_value = {}

        asyncio.run(provider.delete_snapshot("ami-001"))
        ec2.deregister_image.assert_called_once_with(ImageId="ami-001")


# ─── DigitalOcean Provider Tests ───────────────────────────────────


def _make_do_provider():
    """Create a DigitalOceanProvider with mocked pydo client."""
    mock_client = MagicMock()

    with (
        patch(
            "ofx.cloud.providers.digitalocean.DOClient",
            MagicMock(return_value=mock_client),
        ),
        patch("ofx.cloud.providers.digitalocean.get_secret", return_value=""),
    ):
        from ofx.cloud.providers.digitalocean import DigitalOceanProvider

        provider = DigitalOceanProvider(token="test-token")
    provider._client = mock_client
    return provider, mock_client


class TestDOCreateInstance:
    def test_droplet_create_body_builds_optional_fields(self):
        provider, client = _make_do_provider()
        client.ssh_keys.list.return_value = {
            "ssh_keys": [{"id": 111, "name": "my-key", "fingerprint": "aa:bb:cc"}]
        }
        config = _make_cloud_config(
            provider="digitalocean",
            image="ubuntu-22-04-x64",
            ssh_key="my-key",
            vpc_uuid="vpc-abc123",
            project_id="proj-xyz",
            tags=["scan"],
        )

        body = provider._droplet_create_body(config)

        assert body["ssh_keys"] == [111]
        assert body["vpc_uuid"] == "vpc-abc123"
        assert body["project_ids"] == ["proj-xyz"]
        assert "ofx" in body["tags"]
        assert "scan" in body["tags"]

    def test_droplet_create_body_password_auth_sets_user_data(self):
        provider, client = _make_do_provider()
        client.ssh_keys.list.return_value = {"ssh_keys": []}
        config = _make_cloud_config(
            provider="digitalocean",
            image="ubuntu-22-04-x64",
            ssh_password="secret123",
        )

        body = provider._droplet_create_body(config)

        assert "user_data" in body
        assert "secret123" in body["user_data"]
        assert "chpasswd" in body["user_data"]

    def test_basic_create(self):
        provider, client = _make_do_provider()
        client.droplets.create.return_value = {
            "droplet": {"id": 12345, "status": "new"}
        }
        client.ssh_keys.list.return_value = {"ssh_keys": []}

        config = _make_cloud_config(
            provider="digitalocean",
            region="nyc3",
            size="s-1vcpu-1gb",
            image="ubuntu-22-04-x64",
        )
        info = asyncio.run(provider.create_instance(config))

        assert info.instance_id == "12345"
        assert info.provider == "digitalocean"
        assert info.status == "new"
        client.droplets.create.assert_called_once()

        body = client.droplets.create.call_args[1]["body"]
        assert body["region"] == "nyc3"
        assert body["size"] == "s-1vcpu-1gb"
        assert body["image"] == "ubuntu-22-04-x64"
        assert "ofx" in body["tags"]

    def test_create_with_ssh_keys(self):
        provider, client = _make_do_provider()
        client.ssh_keys.list.return_value = {
            "ssh_keys": [
                {"id": 111, "name": "my-key", "fingerprint": "aa:bb:cc"},
                {"id": 222, "name": "other-key", "fingerprint": "dd:ee:ff"},
            ]
        }
        client.droplets.create.return_value = {
            "droplet": {"id": 99999, "status": "new"}
        }

        config = _make_cloud_config(
            provider="digitalocean",
            image="ubuntu-22-04-x64",
            ssh_key="my-key",
        )
        asyncio.run(provider.create_instance(config))

        body = client.droplets.create.call_args[1]["body"]
        assert body["ssh_keys"] == [111]

    def test_create_with_password_auth(self):
        provider, client = _make_do_provider()
        client.ssh_keys.list.return_value = {"ssh_keys": []}
        client.droplets.create.return_value = {
            "droplet": {"id": 88888, "status": "new"}
        }

        config = _make_cloud_config(
            provider="digitalocean",
            image="ubuntu-22-04-x64",
            ssh_password="secret123",
        )
        asyncio.run(provider.create_instance(config))

        body = client.droplets.create.call_args[1]["body"]
        assert "user_data" in body
        assert "secret123" in body["user_data"]
        assert "chpasswd" in body["user_data"]

    def test_create_with_vpc_and_project(self):
        provider, client = _make_do_provider()
        client.ssh_keys.list.return_value = {"ssh_keys": []}
        client.droplets.create.return_value = {
            "droplet": {"id": 77777, "status": "new"}
        }

        config = _make_cloud_config(
            provider="digitalocean",
            image="ubuntu-22-04-x64",
            vpc_uuid="vpc-abc123",
            project_id="proj-xyz",
        )
        asyncio.run(provider.create_instance(config))

        body = client.droplets.create.call_args[1]["body"]
        assert body["vpc_uuid"] == "vpc-abc123"
        assert body["project_ids"] == ["proj-xyz"]


class TestDOGetInstance:
    def test_droplet_info_helper_extracts_fields(self):
        provider, _client = _make_do_provider()
        droplet = {
            "id": 12345,
            "status": "active",
            "name": "ofx-nyc3-1234",
            "region": {"slug": "nyc3"},
            "size_slug": "s-1vcpu-1gb",
            "image": {"slug": "ubuntu-22-04-x64"},
            "tags": ["ofx"],
            "networks": {
                "v4": [
                    {"type": "private", "ip_address": "10.0.0.5"},
                    {"type": "public", "ip_address": "64.23.1.100"},
                ]
            },
        }

        info = provider._droplet_info(droplet)

        assert info.instance_id == "12345"
        assert info.ip == "64.23.1.100"
        assert info.name == "ofx-nyc3-1234"

    def test_get_with_public_ip(self):
        provider, client = _make_do_provider()
        client.droplets.get.return_value = {
            "droplet": {
                "id": 12345,
                "status": "active",
                "name": "ofx-nyc3-1234",
                "region": {"slug": "nyc3"},
                "size_slug": "s-1vcpu-1gb",
                "image": {"slug": "ubuntu-22-04-x64"},
                "tags": ["ofx"],
                "networks": {
                    "v4": [
                        {"type": "private", "ip_address": "10.0.0.5"},
                        {"type": "public", "ip_address": "64.23.1.100"},
                    ]
                },
            }
        }

        info = asyncio.run(provider.get_instance("12345"))
        assert info.ip == "64.23.1.100"
        assert info.status == "active"
        assert info.name == "ofx-nyc3-1234"
        assert info.is_ready is True

    def test_get_no_public_ip(self):
        provider, client = _make_do_provider()
        client.droplets.get.return_value = {
            "droplet": {
                "id": 12345,
                "status": "new",
                "name": "ofx-test",
                "region": {"slug": "nyc3"},
                "size_slug": "s-1vcpu-1gb",
                "image": {"slug": "ubuntu-22-04-x64"},
                "tags": [],
                "networks": {"v4": [{"type": "private", "ip_address": "10.0.0.5"}]},
            }
        }

        info = asyncio.run(provider.get_instance("12345"))
        assert info.ip == ""


class TestDODestroyInstance:
    def test_destroy(self):
        provider, client = _make_do_provider()
        client.droplets.destroy.return_value = None

        asyncio.run(provider.destroy_instance("12345"))
        client.droplets.destroy.assert_called_once_with(droplet_id=12345)


class TestDOListInstances:
    def test_list_all(self):
        provider, client = _make_do_provider()
        client.droplets.list.return_value = {
            "droplets": [
                {
                    "id": 111,
                    "status": "active",
                    "name": "ofx-1",
                    "region": {"slug": "nyc3"},
                    "size_slug": "s-1vcpu-1gb",
                    "tags": ["ofx"],
                    "networks": {"v4": [{"type": "public", "ip_address": "1.1.1.1"}]},
                },
                {
                    "id": 222,
                    "status": "off",
                    "name": "ofx-2",
                    "region": {"slug": "sfo3"},
                    "size_slug": "s-2vcpu-2gb",
                    "tags": ["ofx"],
                    "networks": {"v4": []},
                },
            ]
        }

        instances = asyncio.run(provider.list_instances())
        assert len(instances) == 2
        assert instances[0].ip == "1.1.1.1"
        assert instances[1].ip == ""

    def test_list_with_tag(self):
        provider, client = _make_do_provider()
        client.droplets.list.return_value = {"droplets": []}

        asyncio.run(provider.list_instances(tags=["scan"]))
        client.droplets.list.assert_called_once_with(tag_name="scan")


class TestDOSnapshots:
    def test_create_snapshot(self):
        provider, client = _make_do_provider()
        client.droplet_actions.post.return_value = {
            "action": {"id": 9999, "status": "in-progress"}
        }
        # Mock wait_for_action
        client.actions.get.return_value = {
            "action": {"id": 9999, "status": "completed"}
        }
        client.snapshots.list.return_value = {
            "snapshots": [
                {
                    "id": "snap-001",
                    "name": "my-snap",
                    "size_gigabytes": 25,
                    "created_at": "2024-01-01T00:00:00Z",
                    "regions": ["nyc3"],
                }
            ]
        }

        snap = asyncio.run(provider.create_snapshot("12345", "my-snap"))
        assert snap.name == "my-snap"
        assert snap.snapshot_id == "snap-001"

    def test_action_status_helper(self):
        provider, _client = _make_do_provider()
        assert provider._action_status({"status": "completed"}) == "completed"

    def test_snapshot_helpers(self):
        provider, _client = _make_do_provider()
        snapshot = {
            "id": "snap-001",
            "name": "my-snap",
            "size_gigabytes": 25,
            "created_at": "2024-01-01T00:00:00Z",
            "regions": ["nyc3"],
        }

        info = provider._snapshot_info(snapshot)
        pending = provider._pending_snapshot_info("pending-snap")

        assert info.snapshot_id == "snap-001"
        assert info.region == "nyc3"
        assert pending.status == "in-progress"
        assert provider._snapshot_named([info], "my-snap") is info

    def test_droplet_timeout_error_uses_last_ip(self):
        provider, _client = _make_do_provider()
        error = provider._droplet_timeout_error(
            "12345",
            300,
            provider._droplet_info(
                {
                    "id": 12345,
                    "status": "active",
                    "name": "ofx-nyc3-1234",
                    "region": {"slug": "nyc3"},
                    "size_slug": "s-1vcpu-1gb",
                    "image": {"slug": "ubuntu-22-04-x64"},
                    "tags": ["ofx"],
                    "networks": {"v4": [{"type": "public", "ip_address": "64.23.1.100"}]},
                }
            ),
        )

        assert "64.23.1.100" in str(error)

    def test_list_snapshots(self):
        provider, client = _make_do_provider()
        client.snapshots.list.return_value = {
            "snapshots": [
                {
                    "id": "snap-a",
                    "name": "test-snap",
                    "size_gigabytes": 10,
                    "regions": ["nyc3", "sfo3"],
                    "created_at": "2024-06-01T00:00:00Z",
                },
            ]
        }

        snaps = asyncio.run(provider.list_snapshots())
        assert len(snaps) == 1
        assert snaps[0].snapshot_id == "snap-a"
        assert snaps[0].size_gb == 10
        assert snaps[0].region == "nyc3,sfo3"

    def test_delete_snapshot(self):
        provider, client = _make_do_provider()
        client.snapshots.delete.return_value = None

        asyncio.run(provider.delete_snapshot("snap-001"))
        client.snapshots.delete.assert_called_once_with(snapshot_id="snap-001")


class TestDOWaitForAction:
    def test_action_completes(self):
        provider, client = _make_do_provider()
        call_count = 0

        def mock_get(action_id):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                return {"action": {"id": action_id, "status": "completed"}}
            return {"action": {"id": action_id, "status": "in-progress"}}

        client.actions.get.side_effect = mock_get

        asyncio.run(provider._wait_for_action(9999, timeout=120))
        assert call_count >= 2

    def test_action_errored(self):
        provider, client = _make_do_provider()
        client.actions.get.return_value = {"action": {"id": 9999, "status": "errored"}}

        with pytest.raises(RuntimeError, match="failed"):
            asyncio.run(provider._wait_for_action(9999, timeout=30))


# ─── Provider Initialization Tests ─────────────────────────────────


class TestProviderInit:
    def test_aws_requires_boto3(self):
        with patch("ofx.cloud.providers.aws.boto3", None):
            from ofx.cloud.providers.aws import AWSProvider

            with pytest.raises(ImportError, match="boto3"):
                AWSProvider()

    def test_do_requires_pydo(self):
        with (
            patch("ofx.cloud.providers.digitalocean.DOClient", None),
            patch("ofx.cloud.providers.digitalocean.get_secret", return_value=""),
        ):
            from ofx.cloud.providers.digitalocean import DigitalOceanProvider

            with pytest.raises(ImportError, match="pydo"):
                DigitalOceanProvider(token="test")

    def test_do_requires_token(self):
        mock_client_cls = MagicMock()
        with (
            patch("ofx.cloud.providers.digitalocean.DOClient", mock_client_cls),
            patch("ofx.cloud.providers.digitalocean.get_secret", return_value=""),
            patch.dict("os.environ", {}, clear=True),
        ):
            from ofx.cloud.providers.digitalocean import DigitalOceanProvider

            with pytest.raises(ValueError, match="token required"):
                DigitalOceanProvider(token="")
