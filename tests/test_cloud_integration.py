"""Tests for cloud models, fleet input parsing, and fleet distribution."""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Cloud model tests
# ---------------------------------------------------------------------------


class TestCloudConfig:
    def test_parse_cloud_field_string(self):
        from ofx.models.cloud import parse_cloud_field

        result = parse_cloud_field("my-profile")
        assert result is not None
        assert result.profile == "my-profile"

    def test_parse_cloud_field_dict(self):
        from ofx.models.cloud import parse_cloud_field

        result = parse_cloud_field({
            "provider": "digitalocean",
            "region": "nyc1",
            "size": "s-1vcpu-1gb",
        })
        assert result is not None
        assert result.provider == "digitalocean"
        assert result.region == "nyc1"

    def test_parse_cloud_field_none(self):
        from ofx.models.cloud import parse_cloud_field

        result = parse_cloud_field(None)
        assert result is None

    def test_parse_cloud_field_cloud_config(self):
        from ofx.models.cloud import CloudConfig, parse_cloud_field

        cfg = CloudConfig(provider="aws", region="us-east-1")
        result = parse_cloud_field(cfg)
        assert result is cfg

    def test_cloud_config_winrm_port_auto(self):
        from ofx.models.cloud import CloudConfig

        cfg = CloudConfig(provider="aws", winrm_ssl=True)
        assert cfg.winrm_port == 5986

    def test_cloud_config_extra_fields(self):
        from ofx.models.cloud import CloudConfig

        cfg = CloudConfig(
            provider="digitalocean",
            region="nyc1",
            extra={"token": "abc123"},
        )
        assert cfg.extra["token"] == "abc123"


class TestFleetStrategy:
    def test_fleet_strategy_defaults(self):
        from ofx.models.strategy import FleetStrategy

        fs = FleetStrategy(count=3)
        assert fs.count == 3
        assert fs.distribution == "chunk"
        assert fs.expand_cidrs is True

    def test_fleet_strategy_custom(self):
        from ofx.models.strategy import FleetStrategy

        fs = FleetStrategy(
            count=5,
            input="targets.txt",
            distribution="round-robin",
            expand_cidrs=False,
            exclude=["10.0.0.1"],
        )
        assert fs.count == 5
        assert fs.distribution == "round-robin"
        assert len(fs.exclude) == 1


class TestMatrixStrategyFleet:
    def test_matrix_with_fleet(self):
        from ofx.models.strategy import FleetStrategy, MatrixStrategy

        strategy = MatrixStrategy(
            fleet=FleetStrategy(count=3, input="targets.txt"),
        )
        assert strategy.fleet is not None
        assert strategy.fleet.count == 3
        assert strategy.matrix == {}  # empty default

    def test_matrix_with_both(self):
        from ofx.models.strategy import FleetStrategy, MatrixStrategy

        strategy = MatrixStrategy(
            matrix={"os": ["ubuntu", "debian"]},
            fleet=FleetStrategy(count=2),
        )
        assert len(strategy.matrix["os"]) == 2
        assert strategy.fleet.count == 2


# ---------------------------------------------------------------------------
# Fleet input parser tests
# ---------------------------------------------------------------------------


class TestFleetInputParser:
    def test_parse_single_ip(self):
        from ofx.cloud.fleet_input import FleetInputParser

        parser = FleetInputParser()
        result = parser.parse("192.168.1.1")
        assert result == ["192.168.1.1"]

    def test_parse_comma_separated(self):
        from ofx.cloud.fleet_input import FleetInputParser

        parser = FleetInputParser()
        result = parser.parse("192.168.1.1,192.168.1.2,192.168.1.3")
        assert len(result) == 3

    def test_parse_cidr(self):
        from ofx.cloud.fleet_input import FleetInputParser

        parser = FleetInputParser()
        result = parser.parse("10.0.0.0/30")
        # /30 = 4 IPs, minus network and broadcast = 2 usable
        assert len(result) == 2
        assert "10.0.0.1" in result
        assert "10.0.0.2" in result

    def test_parse_range_full(self):
        from ofx.cloud.fleet_input import FleetInputParser

        parser = FleetInputParser()
        result = parser.parse("10.0.0.1-10.0.0.5")
        assert len(result) == 5
        assert "10.0.0.1" in result
        assert "10.0.0.5" in result

    def test_parse_range_short(self):
        from ofx.cloud.fleet_input import FleetInputParser

        parser = FleetInputParser()
        result = parser.parse("10.0.0.1-5")
        assert len(result) == 5
        assert "10.0.0.1" in result
        assert "10.0.0.5" in result

    def test_parse_hostname(self):
        from ofx.cloud.fleet_input import FleetInputParser

        parser = FleetInputParser()
        result = parser.parse("server1.example.com")
        assert result == ["server1.example.com"]

    def test_parse_file(self, tmp_path):
        from ofx.cloud.fleet_input import FleetInputParser

        targets = tmp_path / "targets.txt"
        targets.write_text("10.0.0.1\n10.0.0.2\n# comment\n\n10.0.0.3\n")

        parser = FleetInputParser()
        result = parser.parse(str(targets))
        assert len(result) == 3

    def test_parse_deduplication(self):
        from ofx.cloud.fleet_input import FleetInputParser

        parser = FleetInputParser()
        result = parser.parse("10.0.0.1,10.0.0.1,10.0.0.2")
        assert len(result) == 2

    def test_parse_exclusion(self):
        from ofx.cloud.fleet_input import FleetInputParser

        parser = FleetInputParser(exclude=["10.0.0.2"])
        result = parser.parse("10.0.0.1,10.0.0.2,10.0.0.3")
        assert len(result) == 2
        assert "10.0.0.2" not in result

    def test_split_subnet(self):
        from ofx.cloud.fleet_input import split_subnet

        result = split_subnet("10.0.0.0/24", count=4, min_prefix=26)
        assert len(result) == 4  # /24 → 4x /26


# ---------------------------------------------------------------------------
# Fleet distributor tests
# ---------------------------------------------------------------------------


class TestFleetDistributor:
    def test_chunk_distribution(self):
        from ofx.cloud.fleet_distributor import FleetDistributor

        dist = FleetDistributor()
        targets = [f"10.0.0.{i}" for i in range(1, 11)]  # 10 targets
        result = dist.distribute(targets, count=3, mode="chunk")
        assert len(result) == 3
        total = sum(len(chunk) for chunk in result)
        assert total == 10

    def test_round_robin_distribution(self):
        from ofx.cloud.fleet_distributor import FleetDistributor

        dist = FleetDistributor()
        targets = [f"10.0.0.{i}" for i in range(1, 7)]  # 6 targets
        result = dist.distribute(targets, count=3, mode="round-robin")
        assert len(result) == 3
        assert all(len(chunk) == 2 for chunk in result)

    def test_line_distribution(self):
        from ofx.cloud.fleet_distributor import FleetDistributor

        dist = FleetDistributor()
        targets = ["line1", "line2", "line3", "line4"]
        result = dist.distribute(targets, count=2, mode="line")
        assert len(result) == 4  # line mode: one chunk per line

    def test_expand_fleet_writes_chunk_files(self):
        from ofx.cloud.fleet_distributor import expand_fleet_to_matrix

        combos, chunk_files = expand_fleet_to_matrix(
            fleet_config={
                "input": ",".join(f"10.0.0.{i}" for i in range(1, 7)),
                "count": 2,
                "distribution": "chunk",
            },
        )
        assert len(chunk_files) == 2
        for f in chunk_files:
            assert f.exists()
        # Cleanup
        for f in chunk_files:
            f.unlink(missing_ok=True)
        chunk_files[0].parent.rmdir()

    def test_expand_fleet_to_matrix(self):
        from ofx.cloud.fleet_distributor import expand_fleet_to_matrix

        result, chunk_files = expand_fleet_to_matrix(
            fleet_config={
                "input": "10.0.0.1,10.0.0.2,10.0.0.3,10.0.0.4",
                "count": 2,
                "distribution": "chunk",
            },
        )
        assert len(result) == 2
        assert "fleet_index" in result[0]
        assert "fleet_total" in result[0]
        assert "fleet_input_file" in result[0]
        assert len(chunk_files) == 2

    def test_subnet_distribution_with_min_prefix(self):
        """Subnet mode groups IPs by configurable prefix length."""
        from ofx.cloud.fleet_distributor import FleetDistributor

        dist = FleetDistributor()
        # /16 prefix — two groups: 10.0.x.x and 10.1.x.x
        targets = [
            "10.0.0.1", "10.0.0.2", "10.0.1.1",  # all 10.0.0.0/16
            "10.1.0.1", "10.1.0.2",                # 10.1.0.0/16
        ]
        result = dist.distribute(targets, count=2, mode="subnet", min_prefix=16)
        assert len(result) == 2
        total = sum(len(c) for c in result)
        assert total == 5

    def test_expand_fleet_min_prefix_passed_through(self):
        """min_prefix from fleet_config is used for subnet grouping."""
        from ofx.cloud.fleet_distributor import expand_fleet_to_matrix

        combos, chunk_files = expand_fleet_to_matrix(
            fleet_config={
                "input": "10.0.0.1,10.0.0.2,10.1.0.1,10.1.0.2",
                "count": 2,
                "distribution": "subnet",
                "min_prefix": 16,
            },
        )
        assert len(combos) == 2
        # Each chunk should have exactly 2 IPs (same /16 grouped together)
        assert combos[0]["fleet_target_count"] == 2
        assert combos[1]["fleet_target_count"] == 2
        for f in chunk_files:
            f.unlink(missing_ok=True)
        if chunk_files:
            chunk_files[0].parent.rmdir()


# ---------------------------------------------------------------------------
# Cloud provider registry tests
# ---------------------------------------------------------------------------


class TestCloudProviderRegistry:
    def test_static_provider_registered(self):
        from ofx.cloud import CloudProviderRegistry

        providers = CloudProviderRegistry.list_providers()
        assert "static" in providers

    def test_create_static(self):
        from ofx.cloud import CloudProviderRegistry

        provider = CloudProviderRegistry.create(
            "static", host="192.168.1.100", user="root"
        )
        assert provider is not None

    def test_unknown_provider_raises(self):
        from ofx.cloud import CloudProviderRegistry

        with pytest.raises(ValueError):
            CloudProviderRegistry.create("nonexistent")


class TestStaticProvider:
    @pytest.mark.asyncio
    async def test_create_instance(self):
        from ofx.cloud.providers.static import StaticProvider
        from ofx.models.cloud import CloudConfig

        provider = StaticProvider(host="10.0.0.1", user="root")
        cfg = CloudConfig(provider="static", host="10.0.0.1", ssh_user="root")
        instance = await provider.create_instance(cfg)
        assert instance.ip == "10.0.0.1"
        assert instance.provider == "static"

    @pytest.mark.asyncio
    async def test_destroy_is_noop(self):
        from ofx.cloud.providers.static import StaticProvider

        provider = StaticProvider(host="10.0.0.1")
        # Should not raise
        await provider.destroy_instance("any-id")

    @pytest.mark.asyncio
    async def test_get_instance(self):
        from ofx.cloud.providers.static import StaticProvider

        provider = StaticProvider(host="10.0.0.1", user="admin", port=2222)
        instance = await provider.get_instance("static-10.0.0.1")
        assert instance is not None
        assert instance.ip == "10.0.0.1"


# ---------------------------------------------------------------------------
# Cloud config profile tests
# ---------------------------------------------------------------------------


class TestCloudProfileManager:
    def test_add_and_list(self, tmp_path):
        from ofx.cloud.config import CloudProfileManager

        mgr = CloudProfileManager(config_path=tmp_path / "cloud.yml")
        mgr.add("test-profile", {"provider": "digitalocean", "region": "nyc1"})
        assert "test-profile" in mgr.list_profiles()

    def test_remove(self, tmp_path):
        from ofx.cloud.config import CloudProfileManager

        mgr = CloudProfileManager(config_path=tmp_path / "cloud.yml")
        mgr.add("to-remove", {"provider": "aws"})
        mgr.remove("to-remove")
        assert "to-remove" not in mgr.list_profiles()

    def test_set_default(self, tmp_path):
        from ofx.cloud.config import CloudProfileManager

        mgr = CloudProfileManager(config_path=tmp_path / "cloud.yml")
        mgr.add("p1", {"provider": "aws"})
        mgr.set_default("p1")
        assert mgr.default_profile_name == "p1"

    def test_resolve_with_profile(self, tmp_path):
        from ofx.cloud.config import CloudProfileManager
        from ofx.models.cloud import CloudConfig

        mgr = CloudProfileManager(config_path=tmp_path / "cloud.yml")
        mgr.add("base", {
            "provider": "digitalocean",
            "region": "nyc1",
            "size": "s-1vcpu-1gb",
            "image": "ubuntu-24-04-x64",
        })

        # Inline config with profile reference
        cfg = CloudConfig(profile="base", size="s-2vcpu-2gb")
        resolved = mgr.resolve(cfg)

        assert resolved.provider == "digitalocean"
        assert resolved.region == "nyc1"
        assert resolved.size == "s-2vcpu-2gb"  # Overridden
        assert resolved.image == "ubuntu-24-04-x64"  # From profile

    def test_as_cloud_config(self, tmp_path):
        from ofx.cloud.config import CloudProfileManager

        mgr = CloudProfileManager(config_path=tmp_path / "cloud.yml")
        mgr.add("test", {"provider": "aws", "region": "us-east-1"})

        cfg = mgr.as_cloud_config("test")
        assert cfg is not None
        assert cfg.provider == "aws"
        assert cfg.region == "us-east-1"

    def test_nonexistent_profile(self, tmp_path):
        from ofx.cloud.config import CloudProfileManager

        mgr = CloudProfileManager(config_path=tmp_path / "cloud.yml")
        assert not mgr.exists("nope")
        with pytest.raises(KeyError):
            mgr.get_profile_data("nope")


# ---------------------------------------------------------------------------
# Cloud instance info tests
# ---------------------------------------------------------------------------


class TestCloudInstanceInfo:
    def test_is_ready(self):
        from ofx.cloud.models import CloudInstanceInfo

        active = CloudInstanceInfo(
            instance_id="i-123", ip="10.0.0.1",
            status="active", provider="do"
        )
        assert active.is_ready

        new = CloudInstanceInfo(
            instance_id="i-456", ip="10.0.0.2",
            status="new", provider="do"
        )
        assert not new.is_ready

    def test_fleet_info(self):
        from ofx.cloud.models import CloudInstanceInfo, FleetInfo

        instances = [
            CloudInstanceInfo(
                instance_id=f"i-{i}", ip=f"10.0.0.{i}",
                status="active", provider="do"
            )
            for i in range(3)
        ]
        fleet = FleetInfo(
            fleet_id="f-1", name="test-fleet",
            provider="do", instances=instances,
        )
        assert fleet.count == 3
        assert len(fleet.ips) == 3
        assert fleet.all_ready


# ---------------------------------------------------------------------------
# Job model cloud field tests
# ---------------------------------------------------------------------------


class TestCloudMatrixFleetModelParsing:
    """Validate that cloud+matrix+fleet workflows parse correctly."""

    def test_cloud_matrix_workflow_parses(self):
        """Cloud+matrix workflow YAML loads into correct model structure."""
        import yaml

        from ofx.models.workflow import Workflow

        wf_yaml = """
name: test-cloud-matrix
jobs:
  scan:
    cloud:
      provider: static
      host: 127.0.0.1
    strategy:
      matrix:
        tool: [nmap, masscan]
        target: [10.0.0.1, 10.0.0.2]
    steps:
      - run: echo test
"""
        wf = Workflow.model_validate(yaml.safe_load(wf_yaml))
        job = wf.jobs["scan"]
        assert job.cloud is not None
        assert job.cloud.provider == "static"
        assert job.strategy is not None
        assert job.strategy.matrix == {"tool": ["nmap", "masscan"], "target": ["10.0.0.1", "10.0.0.2"]}

    def test_cloud_fleet_workflow_parses(self):
        """Cloud+fleet workflow YAML loads into correct model structure."""
        import yaml

        from ofx.models.workflow import Workflow

        wf_yaml = """
name: test-cloud-fleet
jobs:
  recon:
    cloud:
      provider: static
      host: 127.0.0.1
    strategy:
      fleet:
        count: 3
        input: "10.0.0.1,10.0.0.2,10.0.0.3"
        distribution: round-robin
    steps:
      - run: echo test
"""
        wf = Workflow.model_validate(yaml.safe_load(wf_yaml))
        job = wf.jobs["recon"]
        assert job.cloud is not None
        assert job.strategy is not None
        assert job.strategy.fleet is not None
        assert job.strategy.fleet.count == 3
        assert job.strategy.fleet.distribution == "round-robin"

    def test_cloud_matrix_and_fleet_workflow_parses(self):
        """Cloud+matrix+fleet workflow YAML loads into correct model structure."""
        import yaml

        from ofx.models.workflow import Workflow

        wf_yaml = """
name: test-cloud-both
jobs:
  multi:
    cloud:
      provider: static
      host: 127.0.0.1
    strategy:
      matrix:
        tool: [nmap, nuclei]
      fleet:
        count: 2
        input: "10.0.0.1,10.0.0.2,10.0.0.3,10.0.0.4"
        distribution: chunk
    steps:
      - run: echo test
"""
        wf = Workflow.model_validate(yaml.safe_load(wf_yaml))
        job = wf.jobs["multi"]
        assert job.cloud is not None
        assert job.strategy is not None
        assert job.strategy.matrix == {"tool": ["nmap", "nuclei"]}
        assert job.strategy.fleet is not None
        assert job.strategy.fleet.count == 2


class TestJobCloudField:
    def test_job_with_cloud_string(self):
        from ofx.models.job import Job

        job = Job(jid="test", cloud="my-profile", steps=[{"run": "echo hi"}])
        assert job.cloud is not None
        assert job.cloud.profile == "my-profile"

    def test_job_with_cloud_dict(self):
        from ofx.models.job import Job

        job = Job(
            jid="test",
            cloud={"provider": "aws", "region": "us-west-2"},
            steps=[{"run": "echo hi"}],
        )
        assert job.cloud is not None
        assert job.cloud.provider == "aws"

    def test_job_without_cloud(self):
        from ofx.models.job import Job

        job = Job(jid="test", steps=[{"run": "echo hi"}])
        assert job.cloud is None


class TestWaitForLogin:
    """Tests for wait_for_login timeout behaviour."""

    @pytest.mark.asyncio
    async def test_raises_timeout_error_when_login_never_succeeds(self):
        """wait_for_login should raise TimeoutError after timeout, not return False."""
        from ofx.cloud.ssh import wait_for_login
        from ofx.models.cloud import CloudConfig

        cfg = CloudConfig(provider="static", host="10.0.0.99", ssh_key="/tmp/fake.pem")


        async def _failing_probe(*_args, **_kwargs):
            raise ConnectionRefusedError("refused")

        call_count = 0

        async def mock_to_thread(fn, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionRefusedError("refused")

        async def mock_sleep(_delay):
            pass

        with pytest.MonkeyPatch.context() as mp:
            # Patch time so we immediately exceed the timeout
            mp.setattr("ofx.cloud.ssh.time.time", lambda: float(call_count * 10))
            mp.setattr("asyncio.to_thread", mock_to_thread)
            mp.setattr("asyncio.sleep", mock_sleep)

            with pytest.raises(TimeoutError):
                await wait_for_login("10.0.0.99", cfg, timeout=5)

    @pytest.mark.asyncio
    async def test_returns_true_on_successful_login(self):
        """wait_for_login returns True when the probe succeeds immediately."""
        from ofx.cloud.ssh import wait_for_login
        from ofx.models.cloud import CloudConfig

        cfg = CloudConfig(provider="static", host="10.0.0.1", ssh_key="/tmp/fake.pem")

        async def mock_to_thread(fn, *_args, **_kwargs):
            return None  # probe succeeds

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("asyncio.to_thread", mock_to_thread)
            result = await wait_for_login("10.0.0.1", cfg, timeout=30)

        assert result is True


class TestFleetDistributorEdgeCases:
    """Tests for edge cases in FleetDistributor and expand_fleet_to_matrix."""

    def test_distribute_zero_count_returns_empty(self):
        from ofx.cloud.fleet_distributor import FleetDistributor

        d = FleetDistributor()
        assert d.distribute(["10.0.0.1", "10.0.0.2"], count=0) == []

    def test_distribute_no_targets_returns_empty(self):
        from ofx.cloud.fleet_distributor import FleetDistributor

        d = FleetDistributor()
        assert d.distribute([], count=3) == []

    def test_distribute_never_returns_empty_chunks(self):
        """After distribution, no chunk in the result should be empty."""
        from ofx.cloud.fleet_distributor import FleetDistributor

        d = FleetDistributor()
        chunks = d.distribute(["a", "b"], count=5)
        assert all(len(c) > 0 for c in chunks), f"Empty chunk found: {chunks}"
        assert len(chunks) == 2  # capped to target count

    def test_expand_fleet_to_matrix_no_input_returns_empty(self):
        """expand_fleet_to_matrix with no input should return empty, not spawn VPSes."""
        from ofx.cloud.fleet_distributor import expand_fleet_to_matrix

        combos, files = expand_fleet_to_matrix({"count": 3, "input": "", "distribution": "chunk"})
        assert combos == []
        assert files == []

    def test_expand_fleet_to_matrix_no_matching_targets(self):
        """All targets excluded → empty result, no chunk files created."""
        from ofx.cloud.fleet_distributor import expand_fleet_to_matrix

        combos, files = expand_fleet_to_matrix(
            {"count": 2, "input": "10.0.0.1", "distribution": "chunk", "exclude": ["10.0.0.1"]},
        )
        assert combos == []
        assert files == []

    def test_expand_fleet_chunk_files_have_content(self):
        """Chunk files written by expand_fleet_to_matrix contain the targets."""
        import shutil

        from ofx.cloud.fleet_distributor import expand_fleet_to_matrix

        combos, files = expand_fleet_to_matrix(
            {"count": 2, "input": "10.0.0.1,10.0.0.2,10.0.0.3", "distribution": "chunk"}
        )
        try:
            assert len(combos) == 2
            assert len(files) == 2
            total_lines = sum(
                len([line for line in f.read_text().splitlines() if line.strip()])
                for f in files
            )
            assert total_lines == 3
        finally:
            if files:
                shutil.rmtree(str(files[0].parent), ignore_errors=True)
