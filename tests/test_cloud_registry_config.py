"""Tests for CloudProviderRegistry and CloudProfileManager."""

import pytest

from ofx.cloud.base import CloudProvider, CloudProviderRegistry
from ofx.cloud.config import CloudProfileManager
from ofx.models.cloud import CloudConfig

class TestCloudProviderRegistry:
    def setup_method(self):
        """Save and restore registry state to avoid test pollution."""
        self._saved = dict(CloudProviderRegistry._providers)

    def teardown_method(self):
        CloudProviderRegistry._providers = self._saved

    def test_register_and_create(self):
        @CloudProviderRegistry.register("test_provider")
        class TestProvider(CloudProvider):
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def create_instance(self, config):
                pass

            async def wait_until_ready(self, instance_id, timeout=300):
                pass

            async def destroy_instance(self, instance_id):
                pass

            async def get_instance(self, instance_id):
                pass

            async def close(self):
                pass

        provider = CloudProviderRegistry.create("test_provider", token="abc")
        assert isinstance(provider, TestProvider)
        assert provider.kwargs == {"token": "abc"}

    def test_create_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown cloud provider"):
            CloudProviderRegistry.create("nonexistent_provider_xyz")

    def test_list_providers(self):
        result = CloudProviderRegistry.list_providers()
        assert isinstance(result, list)
        assert "static" in result

    def test_get_existing(self):
        cls = CloudProviderRegistry.get("static")
        assert cls is not None

    def test_get_nonexistent(self):
        assert CloudProviderRegistry.get("no_such_provider_xyz") is None

    def test_case_insensitive(self):
        @CloudProviderRegistry.register("CaseMixed")
        class _Dummy(CloudProvider):
            async def create_instance(self, config):
                pass

            async def wait_until_ready(self, instance_id, timeout=300):
                pass

            async def destroy_instance(self, instance_id):
                pass

            async def get_instance(self, instance_id):
                pass

            async def close(self):
                pass

        assert CloudProviderRegistry.get("casemixed") is not None
        assert CloudProviderRegistry.get("CASEMIXED") is not None

    def test_unregister(self):
        @CloudProviderRegistry.register("temp_remove")
        class _Temp(CloudProvider):
            async def create_instance(self, config):
                pass

            async def wait_until_ready(self, instance_id, timeout=300):
                pass

            async def destroy_instance(self, instance_id):
                pass

            async def get_instance(self, instance_id):
                pass

            async def close(self):
                pass

        assert CloudProviderRegistry.get("temp_remove") is not None
        CloudProviderRegistry.unregister("temp_remove")
        assert CloudProviderRegistry.get("temp_remove") is None

    def test_unregister_nonexistent_is_noop(self):
        CloudProviderRegistry.unregister("never_existed_xyz")

    def test_available_provider_names_helper(self):
        names = CloudProviderRegistry._available_provider_names()
        assert "static" in names

    def test_unsupported_snapshot_operation_message(self):
        @CloudProviderRegistry.register("unsupported_test")
        class _Unsupported(CloudProvider):
            async def create_instance(self, config):
                pass

            async def wait_until_ready(self, instance_id, timeout=300):
                pass

            async def destroy_instance(self, instance_id):
                pass

            async def get_instance(self, instance_id):
                pass

            async def close(self):
                pass

        provider = CloudProviderRegistry.create("unsupported_test")
        with pytest.raises(NotImplementedError, match="snapshot creation"):
            import asyncio

            asyncio.run(provider.create_snapshot("i-1", "snap"))

    def test_poll_until_returns_ready_result(self):
        @CloudProviderRegistry.register("poll_test")
        class _PollProvider(CloudProvider):
            async def create_instance(self, config):
                pass

            async def wait_until_ready(self, instance_id, timeout=300):
                pass

            async def destroy_instance(self, instance_id):
                pass

            async def get_instance(self, instance_id):
                pass

            async def close(self):
                pass

        provider = CloudProviderRegistry.create("poll_test")
        attempts = {"count": 0}

        async def _probe():
            attempts["count"] += 1
            return attempts["count"]

        import asyncio

        result = asyncio.run(
            provider._poll_until(
                _probe,
                timeout=1,
                interval=0,
                is_ready=lambda value: value >= 3,
            )
        )

        assert result == 3

class TestCloudProfileManager:
    @pytest.fixture()
    def manager(self, tmp_path):
        config_path = tmp_path / "cloud.yml"
        return CloudProfileManager(config_path=config_path)

    @pytest.fixture()
    def populated_manager(self, tmp_path):
        config_path = tmp_path / "cloud.yml"
        m = CloudProfileManager(config_path=config_path)
        m.add(
            "do-small",
            {
                "provider": "static",
                "host": "10.0.0.1",
                "ssh_user": "root",
            },
        )
        m.add(
            "aws-large",
            {
                "provider": "static",
                "host": "10.0.0.2",
                "ssh_user": "ubuntu",
            },
        )
        return m

    def test_empty_manager(self, manager):
        assert manager.list_profiles() == []
        assert manager.profiles == {}
        assert manager.default_profile_name == ""

    def test_bootstraps_default_cloud_config_on_first_use(self, tmp_path, monkeypatch):
        import ofx.cloud.config as cc

        config_path = tmp_path / ".ofx" / "cloud.yml"
        monkeypatch.setattr(cc, "CLOUD_CONFIG_FILE", config_path)

        manager = cc.CloudProfileManager()

        assert config_path.exists()
        text = config_path.read_text()
        assert "# OFX cloud profiles" in text
        assert "# Example:" in text
        assert manager.list_profiles() == []
        assert manager.default_profile_name == ""

    def test_add_profile(self, manager):
        manager.add("test", {"provider": "static", "host": "1.2.3.4"})
        assert "test" in manager.list_profiles()
        data = manager.get_profile_data("test")
        assert data["provider"] == "static"
        assert data["host"] == "1.2.3.4"

    def test_add_overwrites(self, manager):
        manager.add("test", {"provider": "static", "host": "1.1.1.1"})
        manager.add("test", {"provider": "static", "host": "2.2.2.2"})
        assert manager.get_profile_data("test")["host"] == "2.2.2.2"

    def test_remove_profile(self, populated_manager):
        populated_manager.remove("do-small")
        assert "do-small" not in populated_manager.list_profiles()

    def test_remove_nonexistent_raises(self, manager):
        with pytest.raises(KeyError, match="not found"):
            manager.remove("nope")

    def test_get_profile_data_nonexistent_raises(self, manager):
        with pytest.raises(KeyError, match="not found"):
            manager.get_profile_data("nope")

    def test_list_profiles_sorted(self, populated_manager):
        names = populated_manager.list_profiles()
        assert names == sorted(names)

    def test_set_default(self, populated_manager):
        populated_manager.set_default("do-small")
        assert populated_manager.default_profile_name == "do-small"

    def test_set_default_nonexistent_raises(self, manager):
        with pytest.raises(KeyError, match="not found"):
            manager.set_default("nope")

    def test_exists(self, populated_manager):
        assert populated_manager.exists("do-small") is True
        assert populated_manager.exists("nope") is False

    def test_as_cloud_config(self, populated_manager):
        config = populated_manager.as_cloud_config("do-small")
        assert isinstance(config, CloudConfig)
        assert config.host == "10.0.0.1"
        assert config.ssh_user == "root"

    def test_persistence(self, tmp_path):
        config_path = tmp_path / "cloud.yml"
        m1 = CloudProfileManager(config_path=config_path)
        m1.add("persist-test", {"provider": "static", "host": "5.5.5.5"})

        m2 = CloudProfileManager(config_path=config_path)
        assert m2.exists("persist-test")
        assert m2.get_profile_data("persist-test")["host"] == "5.5.5.5"

    def test_resolve_with_profile(self, populated_manager):
        populated_manager.set_default("do-small")
        config = CloudConfig(profile="do-small")
        resolved = populated_manager.resolve(config)
        assert resolved.host == "10.0.0.1"
        assert resolved.ssh_user == "root"

    def test_resolve_with_overrides(self, populated_manager):
        config = CloudConfig(profile="do-small", ssh_user="admin")
        resolved = populated_manager.resolve(config)
        assert resolved.host == "10.0.0.1"
        assert resolved.ssh_user == "admin"

    def test_resolve_no_profile_passthrough(self, manager):
        config = CloudConfig(provider="static", host="direct.host")
        resolved = manager.resolve(config)
        assert resolved.host == "direct.host"

    def test_resolve_missing_profile_warns(self, manager):
        config = CloudConfig(profile="missing")
        resolved = manager.resolve(config)
        assert resolved is config

    def test_resolve_falls_back_to_default(self, populated_manager):
        populated_manager.set_default("aws-large")
        config = CloudConfig()
        resolved = populated_manager.resolve(config)
        assert resolved.host == "10.0.0.2"

    def test_resolve_profile_name_prefers_explicit_profile(self, populated_manager):
        config = CloudConfig(profile="do-small")
        assert populated_manager._resolve_profile_name(config) == "do-small"

    def test_config_overrides_ignore_profile_field(self, populated_manager):
        config = CloudConfig(profile="do-small", ssh_user="admin")
        overrides = populated_manager._config_overrides(
            config,
            profile_name="do-small",
        )
        assert overrides == {"ssh_user": "admin"}
