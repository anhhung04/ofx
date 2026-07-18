"""Tests for cloud runner classes — CloudFleetRunner and CloudMatrixJobRunner."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ofx.models.strategy import FleetStrategy, MatrixStrategy
from ofx.runner.executors.fleet import FleetExecutor
from ofx.runner.executors.matrix import MatrixExecutor

class TestCloudFleetRunner:
    """Test the fleet expansion logic in CloudFleetRunner."""

    fleet_executor = FleetExecutor()

    @staticmethod
    def _cleanup_chunk_files(runner) -> None:
        from ofx.utils.file_cleanup import remove_files_and_parent_dir

        remove_files_and_parent_dir(
            runner._chunk_files,
            on_error=lambda _message: None,
            file_label="chunk file",
            dir_label="chunk dir",
            clear=runner._chunk_files,
        )

    def _make_runner(self, strategy: MatrixStrategy | None = None):
        """Create a CloudFleetRunner with stubbed parent/context."""
        from ofx.models.job import Job
        from ofx.runner import RunContext
        from ofx.runner.cloud_fleet import CloudFleetRunner

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
        runner = CloudFleetRunner(job, ctx, parent=parent)
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
        combos = self.fleet_executor.expand_fleet(runner)

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

        self._cleanup_chunk_files(runner)

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
        combos = self.fleet_executor.expand_fleet(runner)

        assert len(combos) == 3
        for c in combos:
            assert "fleet_index" in c
            assert "fleet_input_file" in c

        self._cleanup_chunk_files(runner)

    def test_no_fleet_returns_default(self):
        """No fleet → single empty combo."""
        strategy = MatrixStrategy()
        runner = self._make_runner(strategy)
        combos = self.fleet_executor.expand_fleet(runner)
        assert combos == [{}]

    def test_fleet_cleanup(self, tmp_path):
        """Chunk files are cleaned up after _cleanup_chunk_files."""
        targets = tmp_path / "targets.txt"
        targets.write_text("a\nb\nc\nd\n")

        strategy = MatrixStrategy(
            fleet=FleetStrategy(count=2, input=str(targets)),
        )
        runner = self._make_runner(strategy)
        self.fleet_executor.expand_fleet(runner)

        assert all(Path(f).exists() for f in runner._chunk_files)

        self._cleanup_chunk_files(runner)
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
        combos = self.fleet_executor.expand_fleet(runner)

        assert len(combos) == 2
        assert combos[0]["fleet_target_count"] == 2
        assert combos[1]["fleet_target_count"] == 2

        self._cleanup_chunk_files(runner)

    def test_fleet_reduces_count_when_few_targets(self):
        """Fleet count reduced when fewer targets than instances."""
        strategy = MatrixStrategy(
            fleet=FleetStrategy(
                count=10,
                input="10.0.0.1,10.0.0.2",
            ),
        )
        runner = self._make_runner(strategy)
        combos = self.fleet_executor.expand_fleet(runner)

        assert len(combos) == 2
        self._cleanup_chunk_files(runner)

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
        combos = self.fleet_executor.expand_fleet(runner)

        assert len(combos) == 2
        assert combos[0]["fleet_target_count"] == 2
        assert combos[1]["fleet_target_count"] == 2
        self._cleanup_chunk_files(runner)

    @pytest.mark.asyncio
    async def test_post_run_cleans_chunk_files(self, monkeypatch):
        calls: list[list[str]] = []
        runner = SimpleNamespace(
            _chunk_files=["/tmp/chunk-a"],
            _logger=SimpleNamespace(debug=lambda _message: None),
        )

        monkeypatch.setattr(
            "ofx.runner.executors.fleet.remove_files_and_parent_dir",
            lambda chunk_files, **_kwargs: calls.append(list(chunk_files)) or chunk_files.clear(),
        )

        await self.fleet_executor.post_run(runner)

        assert calls == [["/tmp/chunk-a"]]
        assert runner._chunk_files == []

    @pytest.mark.asyncio
    async def test_on_failure_cleans_chunk_files(self, monkeypatch):
        calls: list[list[str]] = []
        runner = SimpleNamespace(
            _chunk_files=["/tmp/chunk-a"],
            _logger=SimpleNamespace(debug=lambda _message: None),
        )

        monkeypatch.setattr(
            "ofx.runner.executors.fleet.remove_files_and_parent_dir",
            lambda chunk_files, **_kwargs: calls.append(list(chunk_files)) or chunk_files.clear(),
        )

        await self.fleet_executor.on_failure(runner)

        assert calls == [["/tmp/chunk-a"]]
        assert runner._chunk_files == []

    @pytest.mark.asyncio
    async def test_run_single_fleet_job_builds_child_context_without_mutating_parent(
        self,
        monkeypatch,
    ):
        from types import SimpleNamespace

        import ofx.runner.cloud_job as cloud_job_module
        from ofx.models.job import Job
        from ofx.runner import RunContext, RunnerStatus, RunResult

        captured = {}

        class _ChildRunner:
            def __init__(self, job_copy, ctx, parent):
                captured["job"] = job_copy
                captured["ctx"] = ctx
                captured["parent"] = parent
                self.ctx = ctx
                self.is_failed = False

            async def run(self):
                return RunResult(name="child", run_id="run-1", status=RunnerStatus.COMPLETED)

        class _Runner:
            def __init__(self):
                self.ctx = RunContext(vars={"base": "keep"})
                self.model = Job(
                    jid="fleet-job",
                    cloud={"provider": "static", "host": "10.0.0.1"},
                    strategy=MatrixStrategy(
                        fleet=FleetStrategy(count=2, input="10.0.0.1,10.0.0.2"),
                    ),
                    steps=[{"run": "echo hi"}],
                )
                self.parent = SimpleNamespace()
                self._runners = {}
        monkeypatch.setattr(cloud_job_module, "CloudJobRunner", _ChildRunner)

        runner = _Runner()
        combo = {
            "fleet_name": "chunk-a",
            "fleet_index": 1,
            "fleet_target_count": 2,
        }

        result = await self.fleet_executor.run_single_fleet_job(runner, 0, combo)

        assert result.status == RunnerStatus.COMPLETED
        assert captured["job"].name == "[fleet-job]{0}"
        assert captured["ctx"].vars["fleet"] == combo
        assert captured["ctx"].vars["strategy"]["fleet"]["count"] == 2
        assert runner.ctx.vars == {"base": "keep"}
        assert "fleet-job_0" in runner._runners

class TestCloudMatrixProduceLog:
    """Test _produce_log helpers for fleet/matrix runners."""

    def test_cloud_fleet_runner_produce_log(self):
        from ofx.models.job import Job
        from ofx.runner import RunContext
        from ofx.runner.cloud_fleet import CloudFleetRunner

        runner = CloudFleetRunner.__new__(CloudFleetRunner)
        runner.model = Job(
            jid="fleet-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            steps=[{"run": "echo hi"}],
        )
        runner.parent = None
        runner.ctx = RunContext()

        msg = runner._produce_log("fleet")
        assert "fleet-job" in msg
        assert "cloud-fleet" in msg

    def test_produce_log_with_fleet_vars(self):
        """_produce_log reads fleet_name from ctx.vars['fleet'], not top-level."""
        from ofx.models.job import Job
        from ofx.models.strategy import MatrixStrategy
        from ofx.runner import RunContext
        from ofx.runner.cloud_matrix import CloudMatrixJobRunner

        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=MatrixStrategy(matrix={"tool": ["nmap"]}),
            steps=[{"run": "echo hi"}],
        )
        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner.model = job
        runner.parent = None
        runner.ctx = RunContext(
            vars={
                "fleet": {
                    "fleet_name": "[scan]{2}",
                    "fleet_index": 2,
                }
            }
        )

        msg = runner._produce_log("test message")
        assert "[scan]{2}" in msg
        assert "cloud-fleet" not in msg

    def test_produce_log_without_fleet(self):
        """_produce_log without fleet shows job id only."""
        from ofx.models.job import Job
        from ofx.models.strategy import MatrixStrategy
        from ofx.runner import RunContext
        from ofx.runner.cloud_matrix import CloudMatrixJobRunner

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

    def test_cloud_job_produce_log_includes_workflow_and_cloud_tag(self):
        from ofx.models.job import Job
        from ofx.runner import RunContext
        from ofx.runner.cloud_job import CloudJobRunner

        class _ParentStub:
            model = type("W", (), {"name": "recon"})()

            def _produce_log(self, msg):
                return msg

        runner = CloudJobRunner.__new__(CloudJobRunner)
        runner.model = Job(
            jid="cloud-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            steps=[{"run": "echo hi"}],
        )
        runner.parent = _ParentStub()
        runner.ctx = RunContext()

        msg = runner._produce_log("hello")
        assert "name=recon | job=cloud-job" in msg
        assert "[cloud]" in msg

class TestFleetSurvivingInstances:
    @pytest.mark.asyncio
    async def test_report_surviving_instances_warns_when_instances_left_running(
        self,
        monkeypatch,
    ):
        from ofx.runner.cloud_job import CloudJobRunner

        warnings: list[str] = []
        child_runner = CloudJobRunner.__new__(CloudJobRunner)
        child_runner._provider = object()
        child_runner._cloud_config = SimpleNamespace(provider="digitalocean", auto_destroy=True)
        child_runner._instance = SimpleNamespace(
            name="scan-node",
            instance_id="i-123",
            provider="digitalocean",
            ip="10.0.0.8",
        )

        runner = SimpleNamespace(
            _runners={"job-1": child_runner},
            _log_warning=warnings.append,
        )

        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        await FleetExecutor().report_surviving_instances(runner)

        assert warnings[0] == (
            "Cloud instances from failed fleet may still be running:\n"
            "  job-1: scan-node [i-123] @ 10.0.0.8 (provider=digitalocean)"
        )
        assert warnings[1] == "Fleet instances left running - destroy manually when done."

    @pytest.mark.asyncio
    async def test_report_surviving_instances_destroys_when_user_confirms(
        self,
        monkeypatch,
    ):
        from ofx.runner.cloud_job import CloudJobRunner

        destroyed: list[str] = []
        child_runner = CloudJobRunner.__new__(CloudJobRunner)
        child_runner._provider = object()
        child_runner._cloud_config = SimpleNamespace(provider="digitalocean", auto_destroy=True)
        child_runner._instance = SimpleNamespace(
            name="scan-node",
            instance_id="i-123",
            provider="digitalocean",
            ip="10.0.0.8",
        )

        async def _destroy_instance(_runner):
            destroyed.append("scan-node")

        child_runner._cloud_executor = SimpleNamespace(destroy_instance=_destroy_instance)
        runner = SimpleNamespace(
            _runners={"job-1": child_runner},
            _log_warning=lambda _message: None,
        )

        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        async def _fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr("asyncio.to_thread", _fake_to_thread)
        monkeypatch.setattr("builtins.input", lambda _prompt: "yes")

        await FleetExecutor().report_surviving_instances(runner)

        assert destroyed == ["scan-node"]

class TestCloudMatrixExecutor:
    """Cloud matrix combinations should dispatch on the cloud runner."""

    @pytest.mark.asyncio
    async def test_matrix_combinations_dispatch_remote_steps(self):
        from ofx.runner.executors.cloud_matrix import CloudMatrixExecutor

        calls = []

        class _Strategy:
            max_parallel = 1
            fail_fast = True

        class _Model:
            jid = "cloud-matrix-job"
            strategy = _Strategy()

        class _Runner:
            name = "runner"
            run_id = "run-id"
            model = _Model()
            _matrix_combinations = [{"tool": "nmap"}, {"tool": "nuclei"}]

            class _CloudExecutor:
                async def dispatch_remote_steps(self, runner, matrix_combo, suffix=""):
                    calls.append((matrix_combo, suffix))

            _cloud_executor = _CloudExecutor()

        await CloudMatrixExecutor().do_run(_Runner())

        assert calls == [
            ({"tool": "nmap"}, "_0"),
            ({"tool": "nuclei"}, "_1"),
        ]

class TestCloudMatrixJobRunnerExecution:
    @pytest.mark.asyncio
    async def test_do_run_dispatches_remote_steps_when_matrix_empty(self):
        from ofx.runner.cloud_matrix import CloudMatrixJobRunner

        calls = []

        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner._matrix_executor = type(
            "_Executor",
            (),
            {
                "generate_matrix_combinations": lambda _self, _runner: [],
                "do_run": lambda *_args, **_kwargs: pytest.fail("should not run matrix executor"),
            },
        )()
        runner.model = SimpleNamespace(name="matrix-job", jid="matrix-job")
        runner._instance = None
        runner._log_info = lambda msg: calls.append(("info", msg))
        runner._log_debug = lambda msg: calls.append(("debug", msg))

        async def _upload_fleet_input():
            calls.append(("upload", None))

        runner._upload_fleet_input = _upload_fleet_input

        async def _dispatch_remote_steps(matrix_combo):
            calls.append(("dispatch", matrix_combo))

        runner._cloud_executor = SimpleNamespace(
            dispatch_remote_steps=lambda _runner, matrix_combo, suffix="": _dispatch_remote_steps(matrix_combo)
        )
        runner._matrix_combinations = []

        await runner._do_run()

        assert runner._matrix_combinations == []
        assert calls[-1] == ("dispatch", None)

class TestCloudMatrixExpansion:
    """Test the matrix expansion logic in CloudMatrixJobRunner."""

    matrix_executor = MatrixExecutor()

    def test_matrix_expansion(self):
        """MatrixExecutor.generate_matrix_combinations produces correct combos."""
        from ofx.models.job import Job
        from ofx.runner.cloud_matrix import CloudMatrixJobRunner

        strategy = MatrixStrategy(
            matrix={"tool": ["nmap", "masscan"], "mode": ["fast", "thorough"]},
        )
        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=strategy,
            steps=[{"run": "echo hi"}],
        )
        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner.model = job
        combos = self.matrix_executor.generate_matrix_combinations(runner)

        assert len(combos) == 4
        for c in combos:
            assert "tool" in c
            assert "mode" in c

    def test_matrix_with_exclude(self):
        """Matrix expansion with exclude filter."""
        from ofx.models.job import Job
        from ofx.runner.cloud_matrix import CloudMatrixJobRunner

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
        combos = self.matrix_executor.generate_matrix_combinations(runner)

        assert len(combos) == 3
        assert {"tool": "masscan", "mode": "thorough"} not in combos

    def test_matrix_with_include(self):
        """Matrix expansion with extra include."""
        from ofx.models.job import Job
        from ofx.runner.cloud_matrix import CloudMatrixJobRunner

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
        combos = self.matrix_executor.generate_matrix_combinations(runner)

        assert len(combos) == 2
        assert {"tool": "nmap"} in combos
        assert {"tool": "nuclei"} in combos

    def test_no_matrix_returns_empty(self):
        """No matrix → empty list."""
        from ofx.models.job import Job
        from ofx.runner.cloud_matrix import CloudMatrixJobRunner

        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=MatrixStrategy(),
            steps=[{"run": "echo hi"}],
        )
        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner.model = job
        combos = self.matrix_executor.generate_matrix_combinations(runner)
        assert combos == []

    @pytest.mark.asyncio
    async def test_pre_run_normalizes_string_matrix_values(self, monkeypatch):
        runner = SimpleNamespace(
            model=SimpleNamespace(
                strategy=SimpleNamespace(
                    matrix={
                        "tool": '["nmap", "masscan"]',
                        "count": "2",
                        "target": "example.com",
                    }
                )
            ),
            _resolve_template_fields=AsyncMock(),
            _log_debug=MagicMock(),
        )
        executor = MatrixExecutor()
        monkeypatch.setattr(executor, "generate_matrix_combinations", lambda _runner: ["combo"])

        await executor.pre_run(runner)

        assert runner.model.strategy.matrix == {
            "tool": ["nmap", "masscan"],
            "count": [2],
            "target": ["example.com"],
        }
        assert runner._matrix_combinations == ["combo"]
        runner._log_debug.assert_called_once_with("Matrix key 'tool' resolved to 2 item(s)")

class TestCloudStepRunnerEnvPrefix:
    """Tests for CloudStepRunner._build_env_prefix and _shell_escape."""

    def _make_step_runner(
        self, ctx_envs: dict | None = None, step_env: dict | None = None
    ):
        """Build a CloudStepRunner with minimal stubs — no real SSH needed."""
        from ofx.models.step import Step
        from ofx.runner import RunContext
        from ofx.runner.cloud_step import CloudStepRunner

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
        for key in (
            "REMOTE_FLEET_INDEX",
            "REMOTE_FLEET_TOTAL",
            "REMOTE_FLEET_TARGET_COUNT",
            "REMOTE_FLEET_INPUT_FILE",
        ):
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
        from ofx.utils.shell import bash_dquote_escape

        assert bash_dquote_escape("$(id)") == "\\$(id)"
        assert bash_dquote_escape("`whoami`") == "\\`whoami\\`"
        assert bash_dquote_escape('say "hi"') == 'say \\"hi\\"'
        assert bash_dquote_escape("a\\b") == "a\\\\b"

    def test_shell_escape_plain_path(self):
        """Normal file paths are unchanged by escaping."""
        from ofx.utils.shell import bash_dquote_escape

        assert (
            bash_dquote_escape("/tmp/.run-abc/fleet_targets.txt")
            == "/tmp/.run-abc/fleet_targets.txt"
        )

class TestCloudMatrixFailFast:
    """Tests for fail_fast behavior in CloudMatrixJobRunner."""

    matrix_executor = MatrixExecutor()

    def _make_runner_with_strategy(self, strategy):
        from ofx.models.job import Job
        from ofx.runner import RunContext
        from ofx.runner.cloud_matrix import CloudMatrixJobRunner

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
        combos = self.matrix_executor.generate_matrix_combinations(runner)
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
        from ofx.models.step import Step
        from ofx.runner import RunContext
        from ofx.runner.cloud_job import CloudJobRunner
        from ofx.runner.cloud_step import CloudStepRunner

        parent_job = object.__new__(CloudJobRunner)
        parent_job._cached_python = None

        step = Step(run="echo hi", step_index=0)
        ctx = RunContext()

        class _FakeRemote:
            def run(self, cmd, timeout=None):
                return "python3 3.11.0"

        step_runner = CloudStepRunner.__new__(CloudStepRunner)
        step_runner.model = step
        step_runner.ctx = ctx
        step_runner.parent = parent_job
        step_runner._remote = _FakeRemote()
        step_runner._work_dir = "/tmp"
        step_runner._log_info = lambda msg: None
        step_runner._log_debug = lambda msg: None
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
        parent_job._cached_python = "python3"

        call_count = 0

        async def mock_to_thread(fn, cmd, timeout):
            nonlocal call_count
            call_count += 1
            return "python3 3.11.0"

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("asyncio.to_thread", mock_to_thread)
            result = await step_runner._discover_python()

        assert result == "python3"
        assert call_count == 0

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
    async def test_fleet_runtime_updates_populate_env_and_vars_without_upload(self):
        from ofx.models.job import Job
        from ofx.runner import RunContext
        from ofx.runner.cloud_job import CloudJobRunner

        job = Job(
            jid="fleet-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            steps=[{"run": "echo hi"}],
        )
        ctx = RunContext()
        ctx.vars["fleet"] = {
            "fleet_name": "chunk-a",
            "fleet_index": 2,
            "fleet_input": ["10.0.0.1", "10.0.0.2"],
        }

        runner = CloudJobRunner.__new__(CloudJobRunner)
        runner.model = job
        runner.ctx = ctx
        runner.parent = None
        runner._remote_runner = None
        runner._work_dir = None
        runner._cloud_config = job.cloud

        await runner._upload_fleet_input()

        assert runner.ctx.envs["REMOTE_FLEET_NAME"] == "chunk-a"
        assert runner.ctx.envs["REMOTE_FLEET_INDEX"] == "2"
        assert runner.ctx.envs["REMOTE_FLEET_INPUT"] == "10.0.0.1\n10.0.0.2"
        assert runner.ctx.vars["remote_fleet_name"] == "chunk-a"
        assert runner.ctx.vars["remote_fleet_index"] == 2
        assert runner.ctx.vars["remote_fleet_input"] == ["10.0.0.1", "10.0.0.2"]
        assert "fleet_name" not in runner.ctx.envs

    @pytest.mark.asyncio
    async def test_upload_fleet_input_sets_remote_path_metadata(self, tmp_path):
        from ofx.models.job import Job
        from ofx.runner import RunContext
        from ofx.runner.cloud_job import CloudJobRunner

        chunk = tmp_path / "chunk.txt"
        chunk.write_text("10.0.0.1\n")

        uploaded: list[tuple[str, str]] = []

        class _Remote:
            def upload(self, src, dst):
                uploaded.append((src, dst))

        job = Job(
            jid="fleet-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            steps=[{"run": "echo hi"}],
        )
        ctx = RunContext()
        ctx.vars["fleet"] = {"fleet_input_file": str(chunk), "fleet_name": "test"}

        runner = CloudJobRunner.__new__(CloudJobRunner)
        runner.model = job
        runner.ctx = ctx
        runner.parent = None
        runner._remote_runner = _Remote()
        runner._work_dir = "/tmp/ofx-run"
        runner._cloud_config = job.cloud
        runner._log_info = lambda _message: None

        await runner._upload_fleet_input()

        assert uploaded == [(str(chunk), "/tmp/ofx-run/fleet_targets.txt")]
        assert runner.ctx.envs["REMOTE_FLEET_INPUT_FILE"] == "/tmp/ofx-run/fleet_targets.txt"
        assert runner.ctx.vars["remote_fleet_input_file"] == "/tmp/ofx-run/fleet_targets.txt"

    def test_remote_fleet_input_path_uses_windows_separator(self):
        from ofx.cloud.runtime import remote_join

        assert (
            remote_join("C:\\ofx-run", "fleet_targets.txt", is_windows=True)
            == "C:\\ofx-run\\fleet_targets.txt"
        )

    def test_remote_input_runtime_updates_can_be_applied_to_runner_context(self):
        from ofx.models.job import Job
        from ofx.runner import RunContext
        from ofx.runner.cloud_job import CloudJobRunner

        runner = CloudJobRunner.__new__(CloudJobRunner)
        runner.model = Job(
            jid="fleet-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            steps=[{"run": "echo hi"}],
        )
        runner.ctx = RunContext()

        runner.update_env_and_vars(
            {"REMOTE_FLEET_INPUT_FILE": "/tmp/fleet_targets.txt"},
            {"remote_fleet_input_file": "/tmp/fleet_targets.txt"},
        )

        assert runner.ctx.envs["REMOTE_FLEET_INPUT_FILE"] == "/tmp/fleet_targets.txt"
        assert runner.ctx.vars["remote_fleet_input_file"] == "/tmp/fleet_targets.txt"

    def test_fleet_input_upload_context_and_messages(self, tmp_path):
        from ofx.cloud.runtime import remote_join
        from ofx.models.job import Job
        from ofx.runner import RunContext
        from ofx.runner.cloud_job import CloudJobRunner

        chunk = tmp_path / "chunk.txt"
        chunk.write_text("10.0.0.1\n")

        runner = CloudJobRunner.__new__(CloudJobRunner)
        runner.model = Job(
            jid="fleet-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            steps=[{"run": "echo hi"}],
        )
        runner.ctx = RunContext(vars={"fleet": {"fleet_input_file": str(chunk)}})
        runner.parent = None
        runner._remote_runner = object()
        runner._work_dir = "/tmp/ofx-run"
        runner._cloud_config = runner.model.cloud

        fleet_vars = runner.ctx.vars["fleet"]
        local_path = str(fleet_vars.get("fleet_input_file", "") or "")
        local = Path(local_path) if local_path else None
        remote_path = remote_join(
            runner._work_dir,
            "fleet_targets.txt",
            is_windows=False,
        )

        assert fleet_vars == {"fleet_input_file": str(chunk)}
        assert local == chunk
        assert remote_path == "/tmp/ofx-run/fleet_targets.txt"
        runner.update_env_and_vars(
            {"REMOTE_FLEET_INPUT_FILE": remote_path},
            {"remote_fleet_input_file": remote_path},
        )
        assert runner.ctx.envs["REMOTE_FLEET_INPUT_FILE"] == remote_path
        assert runner.ctx.vars["remote_fleet_input_file"] == remote_path

    @pytest.mark.asyncio
    async def test_upload_fleet_input_skips_input_file_when_building_runtime_updates(self):
        from ofx.models.job import Job
        from ofx.runner import RunContext
        from ofx.runner.cloud_job import CloudJobRunner

        runner = CloudJobRunner.__new__(CloudJobRunner)
        runner.model = Job(
            jid="fleet-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            steps=[{"run": "echo hi"}],
        )
        runner.ctx = RunContext(
            vars={
                "fleet": {
                    "fleet_input_file": "/tmp/chunk.txt",
                    "fleet_name": "chunk-a",
                    "fleet_index": 2,
                }
            }
        )
        runner.parent = None
        runner._remote_runner = None
        runner._work_dir = None
        runner._cloud_config = runner.model.cloud

        await runner._upload_fleet_input()

        assert "REMOTE_FLEET_INPUT_FILE" not in runner.ctx.envs
        assert runner.ctx.envs["REMOTE_FLEET_NAME"] == "chunk-a"
        assert runner.ctx.envs["REMOTE_FLEET_INDEX"] == "2"

    @pytest.mark.asyncio
    async def test_upload_fleet_input_formats_list_runtime_values(self, tmp_path):
        from ofx.models.job import Job
        from ofx.runner import RunContext
        from ofx.runner.cloud_job import CloudJobRunner

        chunk = tmp_path / "chunk.txt"
        chunk.write_text("10.0.0.1\n")

        class _Remote:
            def upload(self, _src, _dst):
                return None

        runner = CloudJobRunner.__new__(CloudJobRunner)
        runner.model = Job(
            jid="fleet-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            steps=[{"run": "echo hi"}],
        )
        runner.ctx = RunContext(
            vars={
                "fleet": {
                    "fleet_input_file": str(chunk),
                    "fleet_input": ["10.0.0.1", "10.0.0.2"],
                }
            }
        )
        runner.parent = None
        runner._remote_runner = _Remote()
        runner._work_dir = "/tmp/ofx-run"
        runner._cloud_config = runner.model.cloud
        runner._log_info = lambda _message: None

        await runner._upload_fleet_input()

        assert runner.ctx.envs["REMOTE_FLEET_INPUT"] == "10.0.0.1\n10.0.0.2"
        assert runner.ctx.vars["remote_fleet_input"] == ["10.0.0.1", "10.0.0.2"]

    @pytest.mark.asyncio
    async def test_upload_failure_raises(self, tmp_path):
        """If _remote_runner.upload raises, _upload_fleet_input should propagate it."""
        from ofx.models.job import Job
        from ofx.runner import RunContext
        from ofx.runner.cloud_job import CloudJobRunner

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
        from ofx.models.step import Step
        from ofx.runner import RunContext
        from ofx.runner.cloud_step import CloudStepRunner

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
        from ofx.runner import RunnerStatus

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
            _runners = {}

        runner.parent = _ParentStub()
        ctx = runner._run_if_context()
        assert ctx["success"]() is True
        assert ctx["failure"]() is False

    def test_produce_log_includes_step_name_and_run_type(self):
        """Cloud step logs should include index, step name, and run type."""
        runner = self._make_step_runner(step_index=2)
        runner.model.name = "recon-step"
        runner._run_type = None

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
        from ofx.models.cloud import CloudConfig
        from ofx.models.step import Step
        from ofx.runner import RunContext
        from ofx.runner.cloud_job import CloudJobRunner
        from ofx.runner.cloud_step import CloudStepRunner

        class _FakeRemote:
            def run(self, cmd, timeout=None):
                return "ok"

        step = Step(run="echo hi", step_index=0)
        ctx = RunContext()

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
        runner.ctx.envs["SOME_LOCAL_VAR"] = "value"
        prefix = runner._build_env_prefix()
        assert prefix == ""
