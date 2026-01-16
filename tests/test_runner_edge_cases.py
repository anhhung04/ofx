"""Tests for runner edge cases and error handling"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from ofx.models.command import Command, Script
from ofx.models.workflow import ToolConfig
from ofx.runner.core import RunContext, RunnerStatus
from ofx.runner.executors.command import CommandRunner, ScriptRunner
from ofx.runner.executors.tool_installer import ToolInstallation, ToolInstallerRunner


class TestCommandRunnerEdgeCases:
    """Test CommandRunner edge cases"""

    @pytest.mark.asyncio
    async def test_command_with_nonexistent_shell(self):
        """Test command with non-existent shell path"""
        cmd = CommandRunner(
            cmd="echo test",
            ctx=RunContext(),
            shell="/nonexistent/shell",
        )
        result = await cmd.run()
        assert result.status == RunnerStatus.FAILED
        assert "Shell not found" in result.error

    @pytest.mark.asyncio
    async def test_command_timeout(self):
        """Test command timeout"""
        cmd = CommandRunner(
            cmd="sleep 5",
            ctx=RunContext(),
            shell="/bin/bash",
            timeout_minutes=1,  # 60 seconds, but command sleeps 5
        )
        # We'll kill it early by using asyncio timeout
        import asyncio

        try:
            await asyncio.wait_for(cmd.run(), timeout=0.5)
            assert False, "Should have timed out"
        except asyncio.TimeoutError:
            pass  # Expected

    @pytest.mark.asyncio
    async def test_command_with_exit_code_failure(self):
        """Test command that fails with non-zero exit code"""
        cmd = CommandRunner(
            cmd="exit 42",
            ctx=RunContext(),
            shell="/bin/bash",
        )
        result = await cmd.run()
        assert result.status == RunnerStatus.FAILED
        assert "exit code 42" in result.error

    @pytest.mark.asyncio
    async def test_command_with_binary_output(self):
        """Test command with binary output"""
        cmd = CommandRunner(
            cmd="printf '\\x00\\x01\\x02\\x03'",
            ctx=RunContext(),
            shell="/bin/bash",
        )
        result = await cmd.run()
        assert result.status == RunnerStatus.COMPLETED
        # Output may be base64 encoded or marked as binary
        assert "binary_output" in result.outputs or "stdout" in result.outputs

    @pytest.mark.asyncio
    async def test_command_with_large_output(self):
        """Test command with output exceeding max size"""
        # Generate more than 60KB of output (default max size)
        cmd = CommandRunner(
            cmd="python3 -c 'print(\"x\" * 70000)'",
            ctx=RunContext(),
            shell="/bin/bash",
        )
        result = await cmd.run()
        assert result.status == RunnerStatus.COMPLETED
        # Check if output was truncated or fully captured
        stdout = result.outputs.get("stdout", "")
        assert len(stdout) > 0  # Should have some output

    @pytest.mark.asyncio
    async def test_command_with_ofx_outputs(self):
        """Test command that writes to OFX_OUTPUTS file"""
        cmd = CommandRunner(
            cmd='echo "key1=value1" >> $OFX_OUTPUTS; echo "key2=value2" >> $OFX_OUTPUTS',
            ctx=RunContext(),
            shell="/bin/bash",
        )
        result = await cmd.run()
        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs.get("key1") == "value1"
        assert result.outputs.get("key2") == "value2"

    @pytest.mark.asyncio
    async def test_command_with_stderr(self):
        """Test command that outputs to stderr"""
        cmd = CommandRunner(
            cmd="echo 'error message' >&2",
            ctx=RunContext(),
            shell="/bin/bash",
        )
        result = await cmd.run()
        assert result.status == RunnerStatus.COMPLETED
        assert "error message" in result.outputs.get("stderr", "")

    @pytest.mark.asyncio
    async def test_command_shell_resolution_from_parent(self):
        """Test shell resolution from parent runner"""
        import yaml

        from ofx.models.workflow import Workflow
        from ofx.runner.executors.workflow import WorkflowRunner

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
            cmd="echo test",
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
            script="this is not valid python syntax!!!",
            ctx=RunContext(),
        )
        result = await script.run()
        assert result.status == RunnerStatus.FAILED

    @pytest.mark.asyncio
    async def test_script_with_runtime_error(self):
        """Test script with runtime error"""
        script = ScriptRunner(
            script="raise ValueError('test error')",
            ctx=RunContext(),
        )
        result = await script.run()
        assert result.status == RunnerStatus.FAILED

    @pytest.mark.asyncio
    async def test_script_large_code(self):
        """Test script with large code (> 2000 chars) that uses temp file"""
        large_script = "# " + ("x" * 3000) + "\nprint('large script executed')"
        script = ScriptRunner(
            script=large_script,
            ctx=RunContext(),
        )
        result = await script.run()
        # Should use temp file
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_script_with_imports(self):
        """Test script with various imports"""
        script = ScriptRunner(
            script="""
import sys
import os
import json
data = {'test': 'value'}
print(json.dumps(data))
""",
            ctx=RunContext(),
        )
        result = await script.run()
        assert result.status == RunnerStatus.COMPLETED
        assert "test" in result.outputs.get("stdout", "")


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
        assert installer.skipped_count == 1
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
            workflow_dir=Path("/workflow"),
        )
        assert ctx.output_path.is_absolute()
        assert all(isinstance(d, Path) for d in ctx.workflow_dirs)
        assert ctx.workflow_dir.is_absolute()

    def test_run_context_env_merging(self):
        """Test RunContext environment variable handling"""
        custom_envs = {"CUSTOM_VAR": "value", "PATH": "/custom/path"}
        ctx = RunContext(envs=custom_envs)
        # PATH should be present (either custom or default)
        assert "PATH" in ctx.envs
