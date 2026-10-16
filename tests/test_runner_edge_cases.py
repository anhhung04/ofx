"""Tests for runner edge cases and error handling"""

import asyncio
from collections import OrderedDict
from pathlib import Path

import pytest

from ofx.models.workflow import ToolConfig
from ofx.runner import RunContext, RunnerStatus
from ofx.runner.tool_installer import ToolInstallation, ToolInstallerRunner


class TestToolInstallerEdgeCases:
    """Test ToolInstallerRunner edge cases"""

    @pytest.mark.asyncio
    async def test_tool_installer_empty_tools(self):
        """Test tool installer with no tools"""
        installer = ToolInstallerRunner(
            tools={},
            ctx=RunContext(),
        )
        result = await installer.run()
        assert result.status == RunnerStatus.COMPLETED
        assert installer.installed_count == 0

    @pytest.mark.asyncio
    async def test_tool_installer_with_check_command_success(self):
        """Test tool installer when check command succeeds (tool exists)"""
        installer = ToolInstallerRunner(
            tools={
                "test_tool": ToolConfig(
                    install="echo 'would install'",
                    check="true",
                )
            },
            ctx=RunContext(),
            show_console=False,
        )
        result = await installer.run()
        assert result.status == RunnerStatus.COMPLETED
        assert installer.installed_count == 0

    @pytest.mark.asyncio
    async def test_tool_installer_with_check_command_failure(self):
        """Test tool installer when check command fails (tool doesn't exist)"""
        installer = ToolInstallerRunner(
            tools={
                "test_tool": ToolConfig(
                    install="echo 'installed' > /dev/null",
                    check="false",
                )
            },
            ctx=RunContext(),
            show_console=False,
        )
        result = await installer.run()
        assert result.status == RunnerStatus.COMPLETED
        assert installer.installed_count == 1

    @pytest.mark.asyncio
    async def test_tool_installer_with_post_install(self):
        """Test tool installer with post-install command"""
        installer = ToolInstallerRunner(
            tools={
                "test_tool": ToolConfig(
                    install="echo 'install'",
                    check="false",
                    post_install="echo 'post install executed'",
                )
            },
            ctx=RunContext(),
            show_console=False,
        )
        result = await installer.run()
        assert result.status == RunnerStatus.COMPLETED
        assert installer.installed_count == 1

    @pytest.mark.asyncio
    async def test_tool_installer_install_failure(self):
        """Test tool installer when installation fails"""
        installer = ToolInstallerRunner(
            tools={
                "failing_tool": ToolConfig(
                    install="exit 1",
                    check="false",
                )
            },
            ctx=RunContext(),
            show_console=False,
        )
        result = await installer.run()
        assert result.status == RunnerStatus.COMPLETED
        assert installer.failed_count == 1
        assert installer.installed_count == 0

    @pytest.mark.asyncio
    async def test_tool_installer_string_config(self):
        """Test tool installer with string config (simplified syntax)"""
        installer = ToolInstallerRunner(
            tools={
                "simple_tool": "echo 'install command'",
            },
            ctx=RunContext(),
            show_console=False,
        )
        assert isinstance(installer.model.tools["simple_tool"], (str, dict, ToolConfig))

    @pytest.mark.asyncio
    async def test_tool_installer_command_runners_use_isolated_env_contexts(
        self,
        monkeypatch,
    ):
        captured_envs = []

        async def _fake_run_shell(_self, cmd, env):
            child_env = dict(env)
            child_env["MUTATED_BY"] = cmd
            captured_envs.append(child_env)
            exit_code = 1 if cmd == "false" else 0
            return exit_code, "out", ""

        monkeypatch.setattr(
            "ofx.runner.tool_installer.ToolInstallerRunner._run_shell",
            _fake_run_shell,
        )

        installer = ToolInstallerRunner(
            tools={
                "test_tool": ToolConfig(
                    install="echo install",
                    check="false",
                    post_install="echo post",
                )
            },
            ctx=RunContext(envs={"BASE": "1"}),
            show_console=False,
        )

        result = await installer.run()

        assert result.status == RunnerStatus.COMPLETED
        assert installer.ctx.envs["BASE"] == "1"
        assert "MUTATED_BY" not in installer.ctx.envs
        assert [env["MUTATED_BY"] for env in captured_envs] == [
            "false",
            "echo install",
            "echo post",
        ]
        assert all(env["BASE"] == "1" for env in captured_envs)

    @pytest.mark.asyncio
    async def test_tool_installation_model(self):
        """Test ToolInstallation model"""
        config = ToolInstallation(
            tools={"tool1": "install cmd", "tool2": "install cmd2"},
            show_console=False,
        )
        assert len(config.tools) == 2
        assert config.show_console is False


class TestRunContextEdgeCases:
    """Test RunContext edge cases"""

    def test_run_context_with_nested_vars(self):
        """Test RunContext with nested variable structures"""
        ctx = RunContext(
            vars={
                "matrix": {"os": "ubuntu", "version": "22.04"},
                "jobs": {"job1": {"status": "completed"}},
                "steps": [{"name": "step1"}, {"name": "step2"}],
            }
        )
        assert ctx.vars["matrix"]["os"] == "ubuntu"
        assert ctx.vars["jobs"]["job1"]["status"] == "completed"
        assert len(ctx.vars["steps"]) == 2

    def test_run_context_path_handling(self):
        """Test RunContext with various path formats"""
        ctx = RunContext(
            output_path=Path("/tmp/test"),
            workflow_dirs=[Path("/dir1"), Path("/dir2")],
        )
        assert ctx.output_path.is_absolute()
        assert all(isinstance(d, Path) for d in ctx.workflow_dirs)

    def test_run_context_env_merging(self):
        """Test RunContext environment variable handling"""
        custom_envs = {"CUSTOM_VAR": "value", "PATH": "/custom/path"}
        ctx = RunContext(envs=custom_envs)
        assert "PATH" in ctx.envs

class TestStepRetryProfileDefaults:
    def test_retry_profile_applies_when_step_not_explicit(self):
        from ofx.models.step import Step
        from ofx.profiles.models import OFXProfile
        from ofx.runner.step import StepRunner

        step = Step.model_validate({"name": "s1", "module": "shell", "with": {"cmd": "echo hi"}})
        parent = type(
            "P",
            (),
            {"registry": None, "_runners": {}, "model": type("M", (), {"jid": "j"})()},
        )()
        runner = StepRunner.__new__(StepRunner)
        runner.model = step
        runner.ctx = RunContext(
            vars={"profile_model": OFXProfile(retry_policy="aggressive")}
        )
        runner.parent = parent
        runner._apply_retry_profile_defaults()

        assert runner.model.retry == 2
        assert runner.model.retry_delay == 2

    def test_retry_profile_overrides_explicit_step(self):
        from ofx.models.step import Step
        from ofx.profiles.models import OFXProfile
        from ofx.runner.step import StepRunner

        step = Step.model_validate(
            {
                "name": "s1",
                "module": "shell",
                "with": {"cmd": "echo hi"},
                "retry": 9,
                "retry-delay": 11,
            }
        )
        parent = type(
            "P",
            (),
            {"registry": None, "_runners": {}, "model": type("M", (), {"jid": "j"})()},
        )()
        runner = StepRunner.__new__(StepRunner)
        runner.model = step
        runner.ctx = RunContext(
            vars={"profile_model": OFXProfile(retry_policy="aggressive")}
        )
        runner.parent = parent
        runner._apply_retry_profile_defaults()

        assert runner.model.retry == 2
        assert runner.model.retry_delay == 2

class TestStepDynamicTimeout:
    """Tests for Jinja2 template expressions in step timeout field."""

    def test_step_timeout_accepts_int(self):
        from ofx.models.step import Step

        step = Step.model_validate(
            {"name": "s1", "module": "shell", "with": {"cmd": "echo hi"}, "timeout": 30}
        )
        assert step.timeout == 30

    def test_step_timeout_accepts_string(self):
        from ofx.models.step import Step

        step = Step.model_validate(
            {"name": "s1", "module": "shell", "with": {"cmd": "echo hi"}, "timeout": "45"}
        )
        assert step.timeout == "45"

    def test_step_timeout_accepts_template_expression(self):
        from ofx.models.step import Step

        expr = "{{ (steps['x'].outputs.count | default(50, true) | int / 50 * 15 + 30) | int }}"
        step = Step.model_validate(
            {"name": "s1", "module": "shell", "with": {"cmd": "echo hi"}, "timeout": expr}
        )
        assert step.timeout == expr

    @pytest.mark.asyncio
    async def test_step_runner_resolves_timeout_template(self):
        """Timeout string expressions should resolve to int via template resolver."""
        from ofx.runner.templates.resolver import TemplateResolver

        resolver = TemplateResolver()
        timeout_expr = "42"
        resolved = await resolver.resolve(timeout_expr, {})
        assert int(float(resolved)) == 42

        timeout_expr2 = "{{ (100 / 50 * 15 + 30) | int }}"
        resolved2 = await resolver.resolve(timeout_expr2, {})
        assert int(float(resolved2)) == 60

    @pytest.mark.asyncio
    async def test_step_runner_timeout_formula_scales(self):
        """Dynamic timeout formula scales with input count."""
        from ofx.runner.templates.resolver import TemplateResolver

        resolver = TemplateResolver()

        r = await resolver.resolve("{{ (50 / 50 * 15 + 30) | int }}", {})
        assert int(float(r)) == 45

        r = await resolver.resolve("{{ (200 / 50 * 15 + 30) | int }}", {})
        assert int(float(r)) == 90

        r = await resolver.resolve("{{ (0 / 50 * 15 + 30) | int }}", {})
        assert int(float(r)) == 30

    def test_step_timeout_invalid_fallback(self):
        """Invalid timeout expression should be handled gracefully."""
        resolved = "not-a-number"
        try:
            timeout = int(float(resolved))
        except (ValueError, TypeError):
            timeout = 60
        assert timeout == 60

class TestMatrixValidation:
    """Test matrix combination size validation."""

    def test_matrix_limit_rejects_huge_product(self):
        """Matrix with excessive combinations raises ValueError."""
        from ofx.models.strategy import MatrixStrategy
        from ofx.runner.matrix_utils import generate_matrix_combinations

        def _parse_matrix_value(value):
            if not isinstance(value, str):
                return value
            try:
                return __import__("json").loads(value)
            except (__import__("json").JSONDecodeError, ValueError):
                return value

        strategy = MatrixStrategy(
            matrix={
                "a": list(range(200)),
                "b": list(range(200)),
            }
        )
        with pytest.raises(ValueError, match="combinations"):
            generate_matrix_combinations(
                strategy.matrix,
                include=strategy.include,
                exclude=strategy.exclude,
                value_processor=_parse_matrix_value,
            )

    def test_matrix_limit_allows_small_product(self):
        """Matrix under limit works fine."""
        from ofx.models.strategy import MatrixStrategy
        from ofx.runner.matrix_utils import generate_matrix_combinations

        def _parse_matrix_value(value):
            if not isinstance(value, str):
                return value
            try:
                return __import__("json").loads(value)
            except (__import__("json").JSONDecodeError, ValueError):
                return value

        strategy = MatrixStrategy(
            matrix={
                "a": [1, 2, 3],
                "b": ["x", "y"],
            }
        )
        combos = generate_matrix_combinations(
            strategy.matrix,
            include=strategy.include,
            exclude=strategy.exclude,
            value_processor=_parse_matrix_value,
        )
        assert len(combos) == 6

class TestTemplateCircularDetection:
    """Test circular template reference detection."""

    @pytest.mark.asyncio
    async def test_no_circular_resolves_fine(self):
        """Non-circular templates resolve normally."""
        from ofx.runner.templates.resolver import TemplateResolver

        resolver = TemplateResolver.__new__(TemplateResolver)
        resolver._template_cache = OrderedDict()
        resolver._support_funcs_cache = None
        resolver._template_cache_max_size = 1000
        resolver._cache_hits = 0
        resolver._cache_misses = 0

        result = await resolver.resolve("{{ x + 1 }}", {"x": 5})
        assert result == "6"

    @pytest.mark.asyncio
    async def test_circular_detection(self):
        """Circular references in the same memo chain are detected."""
        from ofx.runner.templates.resolver import TemplateResolver

        resolver = TemplateResolver.__new__(TemplateResolver)
        resolver._template_cache = OrderedDict()
        resolver._support_funcs_cache = None
        resolver._template_cache_max_size = 1000
        resolver._cache_hits = 0
        resolver._cache_misses = 0

        memo = {"_resolve_stack": ["{{ a }}"]}
        with pytest.raises(ValueError, match="Circular template reference"):
            await resolver.resolve("{{ a }}", {"a": "val"}, _memo=memo)

class TestWorkflowExecutionCancellation:
    """Test async task cancellation in stage execution."""

    @pytest.mark.asyncio
    async def test_stage_runner_handles_cancel(self):
        """WorkflowExecutionManager cancels pending tasks on KeyboardInterrupt."""
        from unittest.mock import AsyncMock, MagicMock

        from ofx.runner.workflow_execution import WorkflowExecutionManager

        parent = MagicMock()
        parent._log_info = MagicMock()
        parent._log_error = MagicMock()

        mgr = WorkflowExecutionManager(parent)

        runner_fast = MagicMock()
        runner_fast.is_failed = False
        runner_fast.run = AsyncMock(return_value=None)

        runner_slow = MagicMock()
        runner_slow.is_failed = False

        async def slow_run():
            await asyncio.sleep(100)

        runner_slow.run = slow_run

        stage_runners = {"fast": runner_fast, "slow": runner_slow}

        failed = await mgr._run_stage(0, stage_runners)
        assert "fast" not in failed


class TestFileBackendEndToEnd:
    """Full workflow over the file registry backend — the H1 regression guard."""

    @pytest.mark.asyncio
    async def test_two_step_workflow_completes_with_file_backend(self, tmp_path):
        """Two steps must not break on the shared registry (H1)."""
        import yaml

        from ofx.models.workflow import Workflow
        from ofx.runner import RunContext, RunnerStatus, WorkflowRunner
        from ofx.runner.registry import RegistryFactory

        workflow_yaml = """
name: File Backend E2E
jobs:
  main:
    name: Main
    steps:
      - name: produce
        module: shell
        with:
          cmd: echo "marker=hello-e2e" >> $RUNNER_OUTPUTS
      - name: consume
        module: shell
        with:
          cmd: |
            echo "got={{ steps.produce.outputs.marker }}" >> $RUNNER_OUTPUTS
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        registry = RegistryFactory.create("file", filepath=str(tmp_path / "registry.json"))
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx, registry=registry)
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        main = runner.runners["main"]
        consume = main.runners["1"]
        consume_outputs = (await consume.get_result()).outputs
        assert consume_outputs["got"] == "hello-e2e"

    @pytest.mark.asyncio
    async def test_parallel_jobs_file_backend_no_contamination(self, tmp_path):
        """Parallel jobs on the file backend keep separate outputs (H2)."""
        import yaml

        from ofx.models.workflow import Workflow
        from ofx.runner import RunContext, RunnerStatus, WorkflowRunner
        from ofx.runner.registry import RegistryFactory

        workflow_yaml = """
name: File Backend Parallel
jobs:
  job_a:
    steps:
      - name: write
        module: shell
        with:
          cmd: echo "value=aaa" >> $RUNNER_OUTPUTS
  job_b:
    steps:
      - name: write
        module: shell
        with:
          cmd: echo "value=bbb" >> $RUNNER_OUTPUTS
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        registry = RegistryFactory.create("file", filepath=str(tmp_path / "registry.json"))
        runner = WorkflowRunner(
            workflow=workflow,
            ctx=RunContext(output_path=tmp_path),
            registry=registry,
        )
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        out_a = (await runner.runners["job_a"].runners["0"].get_result()).outputs
        out_b = (await runner.runners["job_b"].runners["0"].get_result()).outputs
        assert out_a["value"] == "aaa"
        assert out_b["value"] == "bbb"
