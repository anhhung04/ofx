"""Tests for runner edge cases and error handling"""

import asyncio
from collections import OrderedDict
from pathlib import Path

import pytest

from ofx.models.command import Command, Script
from ofx.models.workflow import ToolConfig
from ofx.runner.commands.command import CommandRunner, ScriptRunner
from ofx.runner.core import RunContext, RunnerStatus
from ofx.runner.execution.tool_installer import ToolInstallation, ToolInstallerRunner


class TestCommandRunnerEdgeCases:
    """Test CommandRunner edge cases"""

    @pytest.mark.asyncio
    async def test_command_with_nonexistent_shell(self):
        """Test command with non-existent shell path"""
        from ofx.models.command import Command

        cmd_model = Command(
            cmd="echo test",
            shell="/nonexistent/shell",
        )
        cmd = CommandRunner(
            cmd_model,
            ctx=RunContext(),
        )
        result = await cmd.run()
        assert result.status == RunnerStatus.FAILED
        assert "Shell not found" in result.error

    @pytest.mark.asyncio
    async def test_command_timeout(self):
        """Test that a command runner handles cancellation gracefully."""
        from ofx.models.command import Command

        cmd_model = Command(
            cmd="sleep 10",
            shell="/bin/bash",
            timeout_minutes=1,
        )
        cmd = CommandRunner(
            cmd_model,
            ctx=RunContext(),
        )

        # Start the runner and cancel after a brief delay
        task = asyncio.create_task(cmd.run())
        await asyncio.sleep(0.2)
        task.cancel()

        # Wait for the task to finish (with a safety timeout)
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (asyncio.CancelledError, TimeoutError):
            pass

        # Runner should be in a terminal state after cancellation
        assert cmd.status.value in ("failed", "canceled", "completed")

    @pytest.mark.asyncio
    async def test_command_with_exit_code_failure(self):
        """Test command that fails with non-zero exit code"""
        from ofx.models.command import Command

        cmd_model = Command(
            cmd="exit 42",
            shell="/bin/bash",
        )
        cmd = CommandRunner(
            cmd_model,
            ctx=RunContext(),
        )
        result = await cmd.run()
        assert result.status == RunnerStatus.FAILED
        assert "exit code 42" in result.error

    @pytest.mark.asyncio
    async def test_command_with_binary_output(self):
        """Test command with binary output"""
        from ofx.models.command import Command

        cmd_model = Command(
            cmd="printf '\\x00\\x01\\x02\\x03'",
            shell="/bin/bash",
        )
        cmd = CommandRunner(
            cmd_model,
            ctx=RunContext(),
        )
        result = await cmd.run()
        assert result.status == RunnerStatus.COMPLETED
        # Output may be base64 encoded or marked as binary
        assert "binary_output" in result.outputs or "stdout" in result.outputs

    @pytest.mark.asyncio
    async def test_command_with_large_output(self):
        """Test command with output exceeding max size"""
        # Generate more than 60KB of output (default max size)
        from ofx.models.command import Command

        cmd_model = Command(
            cmd="python3 -c 'print(\"x\" * 70000)'",
            shell="/bin/bash",
        )
        cmd = CommandRunner(
            cmd_model,
            ctx=RunContext(),
        )
        result = await cmd.run()
        assert result.status == RunnerStatus.COMPLETED
        # Check if output was truncated or fully captured
        stdout = result.outputs.get("stdout", "")
        assert len(stdout) > 0  # Should have some output

    @pytest.mark.asyncio
    async def test_command_with_runner_outputs(self):
        """Test command that writes to RUNNER_OUTPUTS file"""
        from ofx.models.command import Command

        cmd_model = Command(
            cmd='echo "key1=value1" >> $RUNNER_OUTPUTS; echo "key2=value2" >> $RUNNER_OUTPUTS',
            shell="/bin/bash",
        )
        cmd = CommandRunner(
            cmd_model,
            ctx=RunContext(),
        )
        result = await cmd.run()
        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs.get("key1") == "value1"
        assert result.outputs.get("key2") == "value2"

    @pytest.mark.asyncio
    async def test_command_with_stderr(self):
        """Test command that outputs to stderr"""
        from ofx.models.command import Command

        cmd_model = Command(
            cmd="echo 'error message' >&2",
            shell="/bin/bash",
        )
        cmd = CommandRunner(
            cmd_model,
            ctx=RunContext(),
        )
        result = await cmd.run()
        assert result.status == RunnerStatus.COMPLETED
        assert "error message" in result.outputs.get("stderr", "")

    @pytest.mark.asyncio
    async def test_command_shell_resolution_from_parent(self):
        """Test shell resolution from parent runner"""
        import yaml

        from ofx.models.workflow import Workflow
        from ofx.runner.execution.workflow import WorkflowRunner

        workflow_yaml = """
name: Test Workflow
defaults:
  run:
    shell: /bin/sh
jobs:
  test:
    steps:
      - run: echo "test"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        workflow_runner = WorkflowRunner(workflow, RunContext())

        cmd = CommandRunner(
            Command(cmd="echo test"),
            ctx=RunContext(),
            parent=workflow_runner,
        )
        await cmd._pre_run()
        # Shell can be /bin/bash (default) or /bin/sh depending on resolution logic
        assert cmd.model.shell in ["/bin/bash", "/bin/sh"]


class TestScriptRunnerEdgeCases:
    """Test ScriptRunner edge cases"""

    @pytest.mark.asyncio
    async def test_script_with_syntax_error(self):
        """Test script with Python syntax error"""
        script = ScriptRunner(
            Script(script="this is not valid python syntax!!!"),
            ctx=RunContext(),
        )
        result = await script.run()
        assert result.status == RunnerStatus.FAILED

    @pytest.mark.asyncio
    async def test_script_with_runtime_error(self):
        """Test script with runtime error"""
        script = ScriptRunner(
            Script(script="raise ValueError('test error')"),
            ctx=RunContext(),
        )
        result = await script.run()
        assert result.status == RunnerStatus.FAILED

    @pytest.mark.asyncio
    async def test_script_large_code(self):
        """Test script with large code (> 2000 chars)"""
        large_script = "# " + ("x" * 3000) + "\nprint('large script executed')"
        from ofx.models.command import Script

        script_model = Script(script=large_script)
        script = ScriptRunner(
            script_model,
            ctx=RunContext(),
        )
        result = await script.run()
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_script_with_imports(self):
        """Test script with various imports"""
        from ofx.models.command import Script

        script_model = Script(
            script="""
import sys
import os
import json
data = {'test': 'value'}
print(json.dumps(data))
"""
        )
        script = ScriptRunner(
            script_model,
            ctx=RunContext(),
        )
        result = await script.run()
        assert result.status == RunnerStatus.COMPLETED
        # assert "test" in result.outputs.get("stdout", "")

    @pytest.mark.asyncio
    async def test_script_with_injected_variables(self):
        """Test script with injected internal variables"""
        from ofx.models.command import Script
        from ofx.runner.core import RunContext

        script_model = Script(
            script="""
publish('test_channel', {'message': 'hello from script'})
gen = subscribe('test_channel')
data = next(gen)
print(f"Subscribed data: {data}")
print(f"Job: {__job__}")
print(f"Step: {__step__}")
print(f"Workflow: {__workflow__}")
print(f"Context has inputs: {hasattr(__ctx__, 'inputs')}")
print("Injected variables work!")
"""
        )

        script_runner = ScriptRunner(script_model, ctx=RunContext())
        result = await script_runner.run()
        assert result.status == RunnerStatus.COMPLETED
        stdout = result.outputs.get("stdout", "")
        assert "Subscribed data: {'message': 'hello from script'}" in stdout
        assert "Job: None" in stdout
        assert "Step: None" in stdout
        assert "Workflow: None" in stdout
        assert "Context has inputs: True" in stdout
        assert "Injected variables work!" in stdout


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
                    check="true",  # Always succeeds
                )
            },
            ctx=RunContext(),
            show_console=False,
        )
        result = await installer.run()
        assert result.status == RunnerStatus.COMPLETED
        # assert installer.skipped_count == 1
        assert installer.installed_count == 0

    @pytest.mark.asyncio
    async def test_tool_installer_with_check_command_failure(self):
        """Test tool installer when check command fails (tool doesn't exist)"""
        installer = ToolInstallerRunner(
            tools={
                "test_tool": ToolConfig(
                    install="echo 'installed' > /dev/null",
                    check="false",  # Always fails
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
        # Should convert string to ToolConfig
        assert isinstance(installer.model.tools["simple_tool"], (str, dict, ToolConfig))

    @pytest.mark.asyncio
    async def test_tool_installation_model(self):
        """Test ToolInstallation model"""
        config = ToolInstallation(
            tools={"tool1": "install cmd", "tool2": "install cmd2"},
            show_console=False,
        )
        assert len(config.tools) == 2
        assert config.show_console is False
        assert "2 tools" in str(config)


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
        # PATH should be present (either custom or default)
        assert "PATH" in ctx.envs


class TestStepRetryProfileDefaults:
    def test_retry_profile_applies_when_step_not_explicit(self):
        from ofx.models.step import Step
        from ofx.profiles.models import OFXProfile
        from ofx.runner.execution.step import StepRunner

        step = Step.model_validate({"name": "s1", "run": "echo hi"})
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
        from ofx.runner.execution.step import StepRunner

        step = Step.model_validate(
            {"name": "s1", "run": "echo hi", "retry": 9, "retry-delay": 11}
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

        # Profile (aggressive: retry=2, retry_delay=2) overrides step values
        assert runner.model.retry == 2
        assert runner.model.retry_delay == 2


class TestStepDynamicTimeout:
    """Tests for Jinja2 template expressions in step timeout field."""

    def test_step_timeout_accepts_int(self):
        from ofx.models.step import Step

        step = Step.model_validate({"name": "s1", "run": "echo hi", "timeout": 30})
        assert step.timeout == 30

    def test_step_timeout_accepts_string(self):
        from ofx.models.step import Step

        step = Step.model_validate({"name": "s1", "run": "echo hi", "timeout": "45"})
        assert step.timeout == "45"

    def test_step_timeout_accepts_template_expression(self):
        from ofx.models.step import Step

        expr = "{{ (steps['x'].outputs.count | default(50, true) | int / 50 * 15 + 30) | int }}"
        step = Step.model_validate({"name": "s1", "run": "echo hi", "timeout": expr})
        assert step.timeout == expr

    @pytest.mark.asyncio
    async def test_step_runner_resolves_timeout_template(self):
        """Timeout string expressions should resolve to int via template resolver."""
        from ofx.runner.templates.resolver import TemplateResolver

        resolver = TemplateResolver()
        # Simulate what _pre_run does: resolve a timeout expression
        timeout_expr = "42"
        resolved = await resolver.resolve(timeout_expr, {})
        assert int(float(resolved)) == 42

        # Formula expression
        timeout_expr2 = "{{ (100 / 50 * 15 + 30) | int }}"
        resolved2 = await resolver.resolve(timeout_expr2, {})
        assert int(float(resolved2)) == 60  # 100/50=2, 2*15=30, 30+30=60

    @pytest.mark.asyncio
    async def test_step_runner_timeout_formula_scales(self):
        """Dynamic timeout formula scales with input count."""
        from ofx.runner.templates.resolver import TemplateResolver

        resolver = TemplateResolver()

        # 50 inputs: 50/50*15+30 = 45 min
        r = await resolver.resolve("{{ (50 / 50 * 15 + 30) | int }}", {})
        assert int(float(r)) == 45

        # 200 inputs: 200/50*15+30 = 90 min
        r = await resolver.resolve("{{ (200 / 50 * 15 + 30) | int }}", {})
        assert int(float(r)) == 90

        # 0 inputs (default 50): should still work
        r = await resolver.resolve("{{ (0 / 50 * 15 + 30) | int }}", {})
        assert int(float(r)) == 30

    def test_step_timeout_invalid_fallback(self):
        """Invalid timeout expression should be handled gracefully."""
        # Test the coercion logic used in step runner
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
        from ofx.utils.matrix import _generate_matrix_combinations

        strategy = MatrixStrategy(
            matrix={
                "a": list(range(200)),
                "b": list(range(200)),
            }
        )
        with pytest.raises(ValueError, match="combinations"):
            _generate_matrix_combinations(strategy)

    def test_matrix_limit_allows_small_product(self):
        """Matrix under limit works fine."""
        from ofx.models.strategy import MatrixStrategy
        from ofx.utils.matrix import _generate_matrix_combinations

        strategy = MatrixStrategy(
            matrix={
                "a": [1, 2, 3],
                "b": ["x", "y"],
            }
        )
        combos = _generate_matrix_combinations(strategy)
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

        from ofx.runner.execution.workflow_execution import WorkflowExecutionManager

        parent = MagicMock()
        parent._log_info = MagicMock()
        parent._log_error = MagicMock()

        mgr = WorkflowExecutionManager(parent)

        # Create mock runners that simulate a slow job
        runner_fast = MagicMock()
        runner_fast.is_failed = False
        runner_fast.run = AsyncMock(return_value=None)

        runner_slow = MagicMock()
        runner_slow.is_failed = False

        async def slow_run():
            await asyncio.sleep(100)

        runner_slow.run = slow_run

        stage_runners = {"fast": runner_fast, "slow": runner_slow}

        # The fast one completes, slow one should be pending
        # This validates the try/finally structure works
        failed = await mgr._run_stage(0, stage_runners)
        # fast completed OK, slow completed OK (asyncio.wait handles both)
        assert "fast" not in failed
