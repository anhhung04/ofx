"""Tests for cloud runner classes — CloudFleetRunner and CloudMatrixJobRunner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ofx.models.strategy import FleetStrategy, MatrixStrategy


class TestCloudFleetRunner:
    """Test the fleet expansion logic in CloudFleetRunner."""

    def _make_runner(self, strategy: MatrixStrategy | None = None):
        """Create a CloudFleetRunner with stubbed parent/context."""
        from ofx.models.job import Job
        from ofx.runner.core import RunContext
        from ofx.runner.execution.cloud_fleet import CloudFleetRunner

        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=strategy,
            steps=[{"run": "echo hi"}],
        )

        class _ParentStub:
            model = type("W", (), {"name": "test-wf"})()
            runners = {}
            _runners = {}

            def _produce_log(self, msg):
                return msg

        parent = _ParentStub()
        ctx = RunContext()
        runner = CloudFleetRunner(job, ctx, parent=parent)  # type: ignore
        return runner

    def test_fleet_only_expansion(self, tmp_path):
        """Cloud + fleet with no matrix."""
        targets = tmp_path / "targets.txt"
        targets.write_text("10.0.0.1\n10.0.0.2\n10.0.0.3\n10.0.0.4\n")

        strategy = MatrixStrategy(
            fleet=FleetStrategy(
                count=2,
                input=str(targets),
                distribution="chunk",
            ),
        )
        runner = self._make_runner(strategy)
        combos = runner._expand_fleet()

        assert len(combos) == 2
        for c in combos:
            assert "fleet_index" in c
            assert "fleet_total" in c
            assert "fleet_input_file" in c
            assert "fleet_target_count" in c
        assert combos[0]["fleet_index"] == 0
        assert combos[1]["fleet_index"] == 1
        assert combos[0]["fleet_total"] == 2
        assert len(runner._chunk_files) == 2
        for f in runner._chunk_files:
            assert Path(f).exists()

        runner._cleanup_chunk_files()

    def test_fleet_with_matrix_expansion(self, tmp_path):
        """Cloud + matrix + fleet → fleet chunks only (matrix on each VPS)."""
        targets = tmp_path / "targets.txt"
        targets.write_text("10.0.0.1\n10.0.0.2\n10.0.0.3\n")

        strategy = MatrixStrategy(
            matrix={"tool": ["nmap", "masscan"]},
            fleet=FleetStrategy(
                count=3,
                input=str(targets),
                distribution="chunk",
            ),
        )
        runner = self._make_runner(strategy)
        combos = runner._expand_fleet()

        # 3 fleet chunks (matrix combos are handled by CloudMatrixJobRunner)
        assert len(combos) == 3
        for c in combos:
            assert "fleet_index" in c
            assert "fleet_input_file" in c

        runner._cleanup_chunk_files()

    def test_no_fleet_returns_default(self):
        """No fleet → single empty combo."""
        strategy = MatrixStrategy()
        runner = self._make_runner(strategy)
        combos = runner._expand_fleet()
        assert combos == [{}]

    def test_fleet_cleanup(self, tmp_path):
        """Chunk files are cleaned up after _cleanup_chunk_files."""
        targets = tmp_path / "targets.txt"
        targets.write_text("a\nb\nc\nd\n")

        strategy = MatrixStrategy(
            fleet=FleetStrategy(count=2, input=str(targets)),
        )
        runner = self._make_runner(strategy)
        runner._expand_fleet()

        assert all(Path(f).exists() for f in runner._chunk_files)

        runner._cleanup_chunk_files()
        assert runner._chunk_files == []

    def test_fleet_ip_input(self):
        """Fleet with inline IP list."""
        strategy = MatrixStrategy(
            fleet=FleetStrategy(
                count=2,
                input="10.0.0.1,10.0.0.2,10.0.0.3,10.0.0.4",
                distribution="round-robin",
            ),
        )
        runner = self._make_runner(strategy)
        combos = runner._expand_fleet()

        assert len(combos) == 2
        assert combos[0]["fleet_target_count"] == 2
        assert combos[1]["fleet_target_count"] == 2

        runner._cleanup_chunk_files()

    def test_fleet_reduces_count_when_few_targets(self):
        """Fleet count reduced when fewer targets than instances."""
        strategy = MatrixStrategy(
            fleet=FleetStrategy(
                count=10,
                input="10.0.0.1,10.0.0.2",
            ),
        )
        runner = self._make_runner(strategy)
        combos = runner._expand_fleet()

        # Only 2 targets → reduced to 2 instances
        assert len(combos) == 2
        runner._cleanup_chunk_files()

    def test_fleet_min_prefix_passed_through(self):
        """min_prefix from FleetStrategy is forwarded to expand_fleet_to_matrix."""
        strategy = MatrixStrategy(
            fleet=FleetStrategy(
                count=2,
                input="10.0.0.1,10.0.0.2,10.1.0.1,10.1.0.2",
                distribution="subnet",
                min_prefix=16,
            ),
        )
        runner = self._make_runner(strategy)
        combos = runner._expand_fleet()

        # Two /16 subnets → two instances, each with 2 targets
        assert len(combos) == 2
        assert combos[0]["fleet_target_count"] == 2
        assert combos[1]["fleet_target_count"] == 2
        runner._cleanup_chunk_files()


class TestCloudMatrixProduceLog:
    """Test _produce_log helpers for fleet/matrix runners."""

    def test_produce_log_with_fleet_vars(self):
        """_produce_log reads fleet_name from ctx.vars['fleet'], not top-level."""
        from ofx.models.job import Job
        from ofx.models.strategy import MatrixStrategy
        from ofx.runner.core import RunContext
        from ofx.runner.execution.cloud_matrix import CloudMatrixJobRunner

        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=MatrixStrategy(matrix={"tool": ["nmap"]}),
            steps=[{"run": "echo hi"}],
        )
        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner.model = job
        runner.parent = None
        runner.ctx = RunContext(vars={
            "fleet": {
                "fleet_name": "[scan]{2}",
                "fleet_index": 2,
            }
        })

        msg = runner._produce_log("test message")
        assert "[scan]{2}" in msg
        assert "cloud-fleet" not in msg

    def test_produce_log_without_fleet(self):
        """_produce_log without fleet shows job id only."""
        from ofx.models.job import Job
        from ofx.models.strategy import MatrixStrategy
        from ofx.runner.core import RunContext
        from ofx.runner.execution.cloud_matrix import CloudMatrixJobRunner

        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=MatrixStrategy(matrix={"tool": ["nmap"]}),
            steps=[{"run": "echo hi"}],
        )
        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner.model = job
        runner.parent = None
        runner.ctx = RunContext()

        msg = runner._produce_log("hello")
        assert "test-job" in msg
        assert "cloud-matrix" in msg


class TestCloudMatrixExpansion:
    """Test the matrix expansion logic in CloudMatrixJobRunner."""

    def test_matrix_expansion(self):
        """CloudMatrixJobRunner._generate_matrix_combinations produces correct combos."""
        from ofx.models.job import Job
        from ofx.runner.execution.cloud_matrix import CloudMatrixJobRunner

        strategy = MatrixStrategy(
            matrix={"tool": ["nmap", "masscan"], "mode": ["fast", "thorough"]},
        )
        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=strategy,
            steps=[{"run": "echo hi"}],
        )
        # We only test the expansion helper, no need for real parent
        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner.model = job
        combos = runner._generate_matrix_combinations()

        assert len(combos) == 4
        for c in combos:
            assert "tool" in c
            assert "mode" in c

    def test_matrix_with_exclude(self):
        """Matrix expansion with exclude filter."""
        from ofx.models.job import Job
        from ofx.runner.execution.cloud_matrix import CloudMatrixJobRunner

        strategy = MatrixStrategy(
            matrix={"tool": ["nmap", "masscan"], "mode": ["fast", "thorough"]},
            exclude=[{"tool": "masscan", "mode": "thorough"}],
        )
        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=strategy,
            steps=[{"run": "echo hi"}],
        )
        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner.model = job
        combos = runner._generate_matrix_combinations()

        assert len(combos) == 3
        assert {"tool": "masscan", "mode": "thorough"} not in combos

    def test_matrix_with_include(self):
        """Matrix expansion with extra include."""
        from ofx.models.job import Job
        from ofx.runner.execution.cloud_matrix import CloudMatrixJobRunner

        strategy = MatrixStrategy(
            matrix={"tool": ["nmap"]},
            include=[{"tool": "nuclei"}],
        )
        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=strategy,
            steps=[{"run": "echo hi"}],
        )
        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner.model = job
        combos = runner._generate_matrix_combinations()

        assert len(combos) == 2
        assert {"tool": "nmap"} in combos
        assert {"tool": "nuclei"} in combos

    def test_no_matrix_returns_empty(self):
        """No matrix → empty list."""
        from ofx.models.job import Job
        from ofx.runner.execution.cloud_matrix import CloudMatrixJobRunner

        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=MatrixStrategy(),
            steps=[{"run": "echo hi"}],
        )
        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner.model = job
        combos = runner._generate_matrix_combinations()
        assert combos == []


class TestCloudStepRunnerEnvPrefix:
    """Tests for CloudStepRunner._build_env_prefix and _shell_escape."""

    def _make_step_runner(self, ctx_envs: dict | None = None, step_env: dict | None = None):
        """Build a CloudStepRunner with minimal stubs — no real SSH needed."""
        from ofx.models.step import Step
        from ofx.runner.core import RunContext
        from ofx.runner.execution.cloud_step import CloudStepRunner

        step = Step(step_index=0, run="echo hi", env=step_env or {})

        class _ParentStub:
            model = type("J", (), {"jid": "job", "env": {}, "defaults": None})()
            registry = None

            def _produce_log(self, msg):
                return msg

        ctx = RunContext(envs=dict(ctx_envs or {}))
        runner = CloudStepRunner.__new__(CloudStepRunner)
        runner.model = step
        runner.ctx = ctx
        runner.parent = _ParentStub()
        runner._remote = None
        runner._work_dir = "/tmp/.run-test"
        runner._run_type = None
        return runner

    def test_remote_fleet_input_file_is_exported(self):
        """REMOTE_FLEET_INPUT_FILE set in ctx.envs must appear in the env prefix."""
        runner = self._make_step_runner(
            ctx_envs={"REMOTE_FLEET_INPUT_FILE": "/tmp/.run-abc/fleet_targets.txt"}
        )
        prefix = runner._build_env_prefix()
        assert "REMOTE_FLEET_INPUT_FILE" in prefix
        assert "/tmp/.run-abc/fleet_targets.txt" in prefix

    def test_remote_fleet_vars_are_exported(self):
        """All REMOTE_FLEET_* vars set by _upload_fleet_input are exported."""
        runner = self._make_step_runner(
            ctx_envs={
                "REMOTE_FLEET_INDEX": "2",
                "REMOTE_FLEET_TOTAL": "5",
                "REMOTE_FLEET_TARGET_COUNT": "10",
                "REMOTE_FLEET_INPUT_FILE": "/tmp/fleet.txt",
            }
        )
        prefix = runner._build_env_prefix()
        for key in ("REMOTE_FLEET_INDEX", "REMOTE_FLEET_TOTAL", "REMOTE_FLEET_TARGET_COUNT", "REMOTE_FLEET_INPUT_FILE"):
            assert key in prefix

    def test_fleet_prefix_vars_still_exported(self):
        """Legacy FLEET_* prefix still exported."""
        runner = self._make_step_runner(ctx_envs={"FLEET_INDEX": "0"})
        prefix = runner._build_env_prefix()
        assert "FLEET_INDEX" in prefix

    def test_non_fleet_ctx_envs_not_leaked(self):
        """Env vars without known prefixes (e.g. PATH, HOME) are not exported."""
        runner = self._make_step_runner(
            ctx_envs={"PATH": "/usr/bin", "SECRET_KEY": "s3cr3t"}
        )
        prefix = runner._build_env_prefix()
        assert "PATH" not in prefix
        assert "SECRET_KEY" not in prefix

    def test_step_env_overrides_ctx_env(self):
        """Step-level env takes precedence over runner-injected ctx envs."""
        runner = self._make_step_runner(
            ctx_envs={"REMOTE_FLEET_INPUT_FILE": "/tmp/old.txt"},
            step_env={"REMOTE_FLEET_INPUT_FILE": "/tmp/new.txt"},
        )
        prefix = runner._build_env_prefix()
        assert "/tmp/new.txt" in prefix
        assert "/tmp/old.txt" not in prefix

    def test_empty_envs_returns_empty_string(self):
        runner = self._make_step_runner()
        assert runner._build_env_prefix() == ""

    def test_shell_escape_prevents_injection(self):
        """Values with $, backticks, and double-quotes are escaped."""
        from ofx.runner.execution.cloud_step import _shell_escape

        assert _shell_escape("$(id)") == "\\$(id)"
        assert _shell_escape("`whoami`") == "\\`whoami\\`"
        assert _shell_escape('say "hi"') == 'say \\"hi\\"'
        assert _shell_escape("a\\b") == "a\\\\b"

    def test_shell_escape_plain_path(self):
        """Normal file paths are unchanged by escaping."""
        from ofx.runner.execution.cloud_step import _shell_escape

        assert _shell_escape("/tmp/.run-abc/fleet_targets.txt") == "/tmp/.run-abc/fleet_targets.txt"


class TestCloudMatrixFailFast:
    """Tests for fail_fast behavior in CloudMatrixJobRunner."""

    def _make_runner_with_strategy(self, strategy):
        from ofx.models.job import Job
        from ofx.runner.core import RunContext
        from ofx.runner.execution.cloud_matrix import CloudMatrixJobRunner

        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=strategy,
            steps=[{"run": "echo hi"}],
        )

        class _ParentStub:
            model = type("W", (), {"name": "test-wf"})()
            runners = {}
            _runners = {}
            def _produce_log(self, msg): return msg

        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner.model = job
        runner.ctx = RunContext()
        runner.parent = _ParentStub()
        runner._instance = type("I", (), {"ip": "10.0.0.1"})()
        return runner

    def test_generate_matrix_combinations_with_fail_fast(self):
        """fail_fast=True (default) is accessible on strategy for matrix runner."""
        from ofx.models.strategy import MatrixStrategy

        strategy = MatrixStrategy(
            matrix={"tool": ["nmap", "masscan"]},
            fail_fast=True,
        )
        runner = self._make_runner_with_strategy(strategy)
        combos = runner._generate_matrix_combinations()
        assert len(combos) == 2

        assert getattr(runner.model.strategy, "fail_fast", True) is True

    def test_generate_matrix_combinations_fail_fast_false(self):
        """fail_fast=False is reflected in strategy."""
        from ofx.models.strategy import MatrixStrategy

        strategy = MatrixStrategy(
            matrix={"tool": ["nmap", "masscan"]},
            fail_fast=False,
        )
        runner = self._make_runner_with_strategy(strategy)
        assert runner.model.strategy.fail_fast is False


class TestDiscoverPythonCache:
    """Tests that _discover_python caches its result at the parent job level."""

    def _make_step_runner_with_parent(self):
        """Return a CloudStepRunner whose parent is a minimal CloudJobRunner stub."""
        from ofx.runner.execution.cloud_step import CloudStepRunner
        from ofx.runner.execution.cloud_job import CloudJobRunner
        from ofx.runner.core import RunContext
        from ofx.models.step import Step

        # Minimal CloudJobRunner stub — only needs _cached_python
        parent_job = object.__new__(CloudJobRunner)
        parent_job._cached_python = None

        step = Step(run="echo hi", step_index=0)
        ctx = RunContext()

        class _FakeRemote:
            def run(self, cmd, timeout=None):  # noqa: D401
                return "python3 3.11.0"

        step_runner = CloudStepRunner.__new__(CloudStepRunner)
        step_runner.model = step
        step_runner.ctx = ctx
        step_runner.parent = parent_job
        step_runner._remote = _FakeRemote()
        step_runner._work_dir = "/tmp"
        step_runner._log_info = lambda msg: None  # avoid BaseRunner slot access
        return step_runner, parent_job

    @pytest.mark.asyncio
    async def test_discover_python_caches_on_parent(self):
        """After discovery the result is stored on the parent job runner."""
        step_runner, parent_job = self._make_step_runner_with_parent()

        call_count = 0

        async def mock_to_thread(fn, cmd, timeout):
            nonlocal call_count
            call_count += 1
            return "python3 3.11.0"

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("asyncio.to_thread", mock_to_thread)
            result = await step_runner._discover_python()

        assert result == "python3"
        assert parent_job._cached_python == "python3"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_discover_python_uses_parent_cache_on_second_step(self):
        """Second CloudStepRunner reuses parent cache without probing remote."""
        step_runner, parent_job = self._make_step_runner_with_parent()
        parent_job._cached_python = "python3"  # pre-populated

        call_count = 0

        async def mock_to_thread(fn, cmd, timeout):
            nonlocal call_count
            call_count += 1
            return "python3 3.11.0"

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("asyncio.to_thread", mock_to_thread)
            result = await step_runner._discover_python()

        assert result == "python3"
        assert call_count == 0  # no SSH probe needed

    @pytest.mark.asyncio
    async def test_discover_python_raises_when_none_found(self):
        """RuntimeError raised when no Python candidate responds."""
        step_runner, parent_job = self._make_step_runner_with_parent()

        async def mock_to_thread(fn, cmd, timeout):
            raise ConnectionError("host unreachable")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("asyncio.to_thread", mock_to_thread)
            with pytest.raises(RuntimeError, match="No python3 or python"):
                await step_runner._discover_python()


class TestFleetInputUploadFailure:
    """Tests that fleet input upload failure raises, not warns."""

    @pytest.mark.asyncio
    async def test_upload_failure_raises(self, tmp_path):
        """If _remote_runner.upload raises, _upload_fleet_input should propagate it."""
        from ofx.runner.execution.cloud_job import CloudJobRunner
        from ofx.runner.core import RunContext
        from ofx.models.job import Job

        # Create a real chunk file to pass the is_file() check
        chunk = tmp_path / "chunk.txt"
        chunk.write_text("10.0.0.1\n")

        job = Job(
            jid="fleet-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            steps=[{"run": "echo hi"}],
        )
        ctx = RunContext()
        ctx.vars["fleet"] = {"fleet_input_file": str(chunk), "fleet_name": "test"}

        class _FailingRemote:
            def upload(self, src, dst):
                raise OSError("network error")

        class _ParentStub:
            registry = None
            model = type("W", (), {"name": "wf"})()
            runners = {}
            _runners = {}

        runner = CloudJobRunner.__new__(CloudJobRunner)
        runner.model = job
        runner.ctx = ctx
        runner.parent = _ParentStub()
        runner._remote_runner = _FailingRemote()
        runner._work_dir = "/tmp"
        runner._cloud_config = job.cloud
        runner._cached_python = None

        with pytest.raises(RuntimeError, match="Failed to upload fleet input file"):
            await runner._upload_fleet_input()


class TestCloudStepRunIfContext:
    """Tests that _run_if_context builds the correct helpers for cloud steps."""

    def _make_step_runner(self, step_index: int = 0):
        from ofx.runner.execution.cloud_step import CloudStepRunner
        from ofx.runner.core import RunContext, RunnerStatus
        from ofx.models.step import Step

        step = Step(run="echo hi", step_index=step_index)
        ctx = RunContext()

        step_runner = CloudStepRunner.__new__(CloudStepRunner)
        step_runner.model = step
        step_runner.ctx = ctx
        parent_job = type("ParentJobStub", (), {})()
        parent_job.model = type("JobModelStub", (), {"jid": "job-a"})()
        parent_job.parent = type("ParentWorkflowStub", (), {})()
        parent_job.parent.model = type("WorkflowModelStub", (), {"name": "wf-a"})()
        parent_job._produce_log = lambda msg: msg
        step_runner.parent = parent_job
        step_runner._remote = None
        step_runner._work_dir = "/tmp"
        return step_runner

    def _make_prev_runner_stub(self, *, is_success=True, is_failed=False):
        from ofx.runner.core import RunnerStatus

        class _Stub:
            pass

        stub = _Stub()
        stub.is_success = is_success
        stub.is_failed = is_failed
        stub.status = RunnerStatus.COMPLETED if is_success else RunnerStatus.FAILED
        return stub

    def test_first_step_defaults_to_success_true(self):
        """Step at index 0 with no parent: success() is True, failure() is False."""
        runner = self._make_step_runner(step_index=0)
        ctx = runner._run_if_context()
        assert ctx["success"]() is True
        assert ctx["failure"]() is False
        assert ctx["canceled"]() is False
        assert ctx["always"]() is True

    def test_second_step_reads_prev_runner_status(self):
        """Step at index 1 reads previous runner's status from parent._runners."""
        runner = self._make_step_runner(step_index=1)

        class _ParentStub:
            _runners = {}

        parent = _ParentStub()
        prev_stub = self._make_prev_runner_stub(is_success=False, is_failed=True)
        parent._runners["0"] = prev_stub
        runner.parent = parent

        ctx = runner._run_if_context()
        assert ctx["success"]() is False
        assert ctx["failure"]() is True
        assert ctx["always"]() is True

    def test_no_prev_runner_found_returns_defaults(self):
        """If parent has no previous runner entry, defaults to success=True."""
        runner = self._make_step_runner(step_index=2)

        class _ParentStub:
            _runners = {}  # step 1 not present

        runner.parent = _ParentStub()
        ctx = runner._run_if_context()
        assert ctx["success"]() is True
        assert ctx["failure"]() is False

    def test_produce_log_includes_step_name_and_run_type(self):
        """Cloud step logs should include index, step name, and run type."""
        runner = self._make_step_runner(step_index=2)
        runner.model.name = "recon-step"
        runner._run_type = None  # force fallback path

        msg = runner._produce_log("hello")
        assert "workflow[wf-a]" in msg
        assert "job[job-a]" in msg
        assert "step[2]" in msg
        assert "[recon-step]" in msg
        assert "[command]" in msg
        assert "hello" in msg


class TestCloudStepWindowsSupport:
    """Tests for Windows-specific (WinRM) env prefix and command formatting."""

    def _make_runner(self, connection_type: str = "ssh"):
        from ofx.runner.execution.cloud_step import CloudStepRunner
        from ofx.runner.execution.cloud_job import CloudJobRunner
        from ofx.runner.core import RunContext
        from ofx.models.step import Step
        from ofx.models.cloud import CloudConfig

        class _FakeRemote:
            def run(self, cmd, timeout=None):
                return "ok"

        step = Step(run="echo hi", step_index=0)
        ctx = RunContext()

        # Parent CloudJobRunner stub with _cloud_config
        parent_job = object.__new__(CloudJobRunner)
        parent_job._cached_python = None
        parent_job._cloud_config = CloudConfig(
            provider="static",
            host="10.0.0.1",
            connection_type=connection_type,
        )

        step_runner = CloudStepRunner.__new__(CloudStepRunner)
        step_runner.model = step
        step_runner.ctx = ctx
        step_runner.parent = parent_job
        step_runner._remote = _FakeRemote()
        step_runner._work_dir = "C:\\ofx" if connection_type == "winrm" else "/tmp/run"
        step_runner._log_info = lambda msg: None
        return step_runner

    def test_is_windows_true_for_winrm(self):
        runner = self._make_runner("winrm")
        assert runner._is_windows is True

    def test_is_windows_false_for_ssh(self):
        runner = self._make_runner("ssh")
        assert runner._is_windows is False

    def test_build_env_prefix_windows_uses_set(self):
        runner = self._make_runner("winrm")
        runner.ctx.envs["REMOTE_FLEET_INPUT_FILE"] = "C:\\targets.txt"
        prefix = runner._build_env_prefix()
        assert "SET REMOTE_FLEET_INPUT_FILE=C:\\targets.txt" in prefix
        assert "export" not in prefix

    def test_build_env_prefix_linux_uses_export(self):
        runner = self._make_runner("ssh")
        runner.ctx.envs["REMOTE_FLEET_INPUT_FILE"] = "/tmp/targets.txt"
        prefix = runner._build_env_prefix()
        assert prefix.startswith("export")
        assert "SET" not in prefix

    def test_build_env_prefix_empty_when_no_fleet_vars(self):
        runner = self._make_runner("winrm")
        runner.ctx.envs["SOME_LOCAL_VAR"] = "value"  # not FLEET_ or REMOTE_
        prefix = runner._build_env_prefix()
        assert prefix == ""
