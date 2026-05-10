"""Tests for runner services: CloudProvisioner, SecretRedactor."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ofx.models.cloud import CloudConfig
from ofx.runner.services.cloud_provisioner import CloudProvisioner
from ofx.runner.services.secret_redactor import SecretRedactor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeInstance:
    instance_id: str = "abc12345-6789"
    name: str = "test-vps"
    ip: str = "1.2.3.4"
    provider: str = "fake"


class FakeProvider:
    """Minimal async provider stub."""

    def __init__(self, instance: FakeInstance | None = None):
        self._instance = instance or FakeInstance()

    async def create_instance(self, _cfg):
        return self._instance

    async def wait_until_ready(self, _id, timeout=300):
        return self._instance

    async def get_instance(self, _id):
        return self._instance

    async def destroy_instance(self, _id):
        pass

    async def close(self):
        pass


class FakeRegistry:
    """Mock provider registry."""

    def __init__(self, provider: FakeProvider | None = None):
        self._provider = provider or FakeProvider()

    def create(self, _name, **_kwargs):
        return self._provider


# =========================================================================
# CloudProvisioner
# =========================================================================


class TestCloudProvisionerBuildKwargs:
    """Tests for _build_provider_kwargs static method."""

    def test_static_provider(self):
        cfg = CloudConfig(
            provider="static",
            host="10.0.0.1",
            ssh_user="admin",
            ssh_port=2222,
            ssh_key="/tmp/id_rsa",
            ssh_password="pass",
        )
        kw = CloudProvisioner._build_provider_kwargs(cfg)
        assert kw["host"] == "10.0.0.1"
        assert kw["user"] == "admin"
        assert kw["port"] == 2222
        assert kw["identity_file"] == "/tmp/id_rsa"
        assert kw["password"] == "pass"

    def test_static_no_key(self):
        cfg = CloudConfig(provider="static", host="10.0.0.1")
        kw = CloudProvisioner._build_provider_kwargs(cfg)
        assert "identity_file" not in kw
        assert "password" not in kw

    def test_digitalocean_provider(self):
        cfg = CloudConfig(provider="digitalocean", extra={"token": "dop_v1_xyz"})
        kw = CloudProvisioner._build_provider_kwargs(cfg)
        assert kw["token"] == "dop_v1_xyz"

    def test_digitalocean_no_token(self):
        cfg = CloudConfig(provider="digitalocean")
        kw = CloudProvisioner._build_provider_kwargs(cfg)
        assert "token" not in kw

    def test_aws_provider(self):
        cfg = CloudConfig(
            provider="aws",
            region="eu-west-1",
            extra={
                "aws_access_key_id": "AKIA",
                "aws_secret_access_key": "secret",
                "region_name": "eu-west-1",
            },
        )
        kw = CloudProvisioner._build_provider_kwargs(cfg)
        assert kw["aws_access_key_id"] == "AKIA"
        assert kw["aws_secret_access_key"] == "secret"
        assert kw["region"] == "eu-west-1"

    def test_aws_default_region(self):
        cfg = CloudConfig(provider="aws")
        kw = CloudProvisioner._build_provider_kwargs(cfg)
        assert kw["region"] == "us-east-1"

    def test_unknown_provider_returns_empty(self):
        cfg = CloudConfig(provider="gcp")
        kw = CloudProvisioner._build_provider_kwargs(cfg)
        assert kw == {}


class TestCloudProvisionerProvision:
    """Tests for the async provision path."""

    @pytest.fixture()
    def provisioner(self):
        return CloudProvisioner(FakeRegistry())

    async def test_provision_static(self, provisioner):
        cfg = CloudConfig(provider="static", host="10.0.0.1", ssh_user="root")
        with (
            patch("ofx.cloud.ssh.wait_for_connectivity", new_callable=AsyncMock),
            patch("ofx.cloud.ssh.wait_for_login", new_callable=AsyncMock),
            patch.object(
                CloudProvisioner, "_create_remote_runner", return_value=MagicMock()
            ),
        ):
            provider, instance, runner, work_dir = await provisioner.provision(cfg)
        assert instance.ip == "1.2.3.4"
        assert work_dir.startswith("/tmp/.run-")

    async def test_provision_non_static_waits(self, provisioner):
        cfg = CloudConfig(provider="digitalocean")
        with (
            patch("ofx.cloud.ssh.wait_for_connectivity", new_callable=AsyncMock),
            patch("ofx.cloud.ssh.wait_for_login", new_callable=AsyncMock),
            patch.object(
                CloudProvisioner, "_create_remote_runner", return_value=MagicMock()
            ),
        ):
            _, instance, _, _ = await provisioner.provision(cfg)
        assert instance.ip == "1.2.3.4"

    async def test_provision_no_ip_raises(self):
        no_ip = FakeInstance(ip="")
        prov = CloudProvisioner(FakeRegistry(FakeProvider(no_ip)))
        cfg = CloudConfig(provider="static", host="")
        with pytest.raises(RuntimeError, match="has no IP address"):
            await prov.provision(cfg)

    async def test_provision_windows_work_dir(self):
        prov = CloudProvisioner(FakeRegistry())
        cfg = CloudConfig(provider="static", host="10.0.0.1", connection_type="winrm")
        with (
            patch("ofx.cloud.ssh.wait_for_connectivity", new_callable=AsyncMock),
            patch("ofx.cloud.ssh.wait_for_login", new_callable=AsyncMock),
            patch.object(
                CloudProvisioner, "_create_remote_runner", return_value=MagicMock()
            ),
        ):
            _, _, _, work_dir = await prov.provision(cfg)
        assert "C:\\Windows\\Temp" in work_dir


class TestCloudProvisionerDestroy:
    """Tests for the destroy path."""

    async def test_destroy_static_noop(self):
        prov = CloudProvisioner(FakeRegistry())
        instance = FakeInstance(provider="static")
        provider = FakeProvider()
        provider.destroy_instance = AsyncMock()
        await prov.destroy(provider, instance)
        provider.destroy_instance.assert_not_called()

    async def test_destroy_calls_provider(self):
        prov = CloudProvisioner(FakeRegistry())
        instance = FakeInstance(provider="digitalocean")
        provider = FakeProvider()
        provider.destroy_instance = AsyncMock()
        await prov.destroy(provider, instance)
        provider.destroy_instance.assert_called_once_with(instance.instance_id)

    async def test_destroy_none_provider(self):
        prov = CloudProvisioner(FakeRegistry())
        await prov.destroy(None, FakeInstance())  # should not raise

    async def test_destroy_none_instance(self):
        prov = CloudProvisioner(FakeRegistry())
        await prov.destroy(FakeProvider(), None)  # should not raise


class TestCloudProvisionerCreateRunner:
    """Tests for _create_remote_runner."""

    def test_creates_ssh_runner(self):
        cfg = CloudConfig(
            provider="static",
            host="10.0.0.1",
            ssh_user="deploy",
            ssh_port=2222,
            ssh_key="/tmp/key",
        )
        with patch("ofx.api.post.RunnerRegistry") as mock_reg:
            mock_reg.create.return_value = MagicMock()
            CloudProvisioner._create_remote_runner(cfg, "10.0.0.1")
            mock_reg.create.assert_called_once()
            call_kwargs = mock_reg.create.call_args
            assert call_kwargs[0][0] == "ssh"
            assert call_kwargs[1]["user"] == "deploy"
            assert call_kwargs[1]["port"] == 2222

    def test_creates_winrm_runner(self):
        cfg = CloudConfig(
            provider="static",
            host="10.0.0.1",
            connection_type="winrm",
            winrm_user="Admin",
            winrm_password="P@ss",
        )
        with patch("ofx.api.post.RunnerRegistry") as mock_reg:
            mock_reg.create.return_value = MagicMock()
            CloudProvisioner._create_remote_runner(cfg, "10.0.0.1")
            call_kwargs = mock_reg.create.call_args
            assert call_kwargs[0][0] == "winrm"
            assert call_kwargs[1]["username"] == "Admin"


# =========================================================================
# SecretRedactor
# =========================================================================


class TestSecretRedactor:
    """Tests for SecretRedactor."""

    def test_register_calls_filter(self):
        with patch("ofx.utils.log.SecretRedactFilter") as mock_filter:
            instance = MagicMock()
            mock_filter.get_instance.return_value = instance
            SecretRedactor.register(["s3cret", "p@ssword"])
            instance.register_values.assert_called_once()
            registered = instance.register_values.call_args[0][0]
            assert "s3cret" in registered
            assert "p@ssword" in registered

    def test_register_filters_empty_and_none(self):
        with patch("ofx.utils.log.SecretRedactFilter") as mock_filter:
            instance = MagicMock()
            mock_filter.get_instance.return_value = instance
            SecretRedactor.register(["secret", "", None])
            registered = instance.register_values.call_args[0][0]
            assert registered == {"secret"}

    def test_register_empty_iterable_noop(self):
        with patch("ofx.utils.log.SecretRedactFilter") as mock_filter:
            instance = MagicMock()
            mock_filter.get_instance.return_value = instance
            SecretRedactor.register([])
            instance.register_values.assert_not_called()

    def test_register_all_none_noop(self):
        with patch("ofx.utils.log.SecretRedactFilter") as mock_filter:
            instance = MagicMock()
            mock_filter.get_instance.return_value = instance
            SecretRedactor.register([None, None, ""])
            instance.register_values.assert_not_called()
