"""Tests for the builtin ``shell`` module (single code path for shell steps).

Covers the features folded in from the removed ``CommandRunner``/
``CommandExecutor``: interactive mode, process-group timeout, output
truncation, ``$RUNNER_OUTPUTS`` capture, streaming via ``ctx.log``, and the
shell-functions preamble. Behavior tests that previously exercised
``CommandRunner`` as a Runner now drive the builtin's ``run(ctx)`` directly or
through :class:`~ofx.modules.runner.ModuleRunner`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ofx.modules import ModuleInvocation, ModuleRunner
from ofx.modules.base import ModuleContext
from ofx.modules.builtins import shell
from ofx.runner import RunContext, RunnerStatus
from ofx.runner.registry_keys import RunnerRegistryKeys


def _ctx(
    args: dict | None = None,
    *,
    env: dict | None = None,
    logger=None,
    interactive: bool = False,
    channels_dir: str | None = None,
) -> ModuleContext:
    return ModuleContext(
        args=dict(args or {}),
        env=dict(env or {}),
        logger=logger,
        interactive=interactive,
        channels_dir=Path(channels_dir) if channels_dir else None,
    )


class TestShellBasic:
    def test_captures_stdout_and_exit_code(self):
        result = shell.run(_ctx({"cmd": "echo hello-basic"}))
        assert result.exit_code == 0
        assert result.stdout.strip() == "hello-basic"
        assert result.stderr == ""

    def test_stderr_captured(self):
        result = shell.run(_ctx({"cmd": "echo oops >&2"}))
        assert result.exit_code == 0
        assert "oops" in result.stderr

    def test_nonzero_exit_code(self):
        result = shell.run(_ctx({"cmd": "exit 42"}))
        assert result.exit_code == 42

    def test_env_vars_passed(self):
        result = shell.run(
            _ctx({"cmd": "echo $MY_TEST_VAR"}, env={"MY_TEST_VAR": "testvalue123"})
        )
        assert "testvalue123" in result.stdout

    def test_working_directory_respected(self, tmp_path):
        result = shell.run(_ctx({"cmd": "pwd"}, env={}))
        assert result.exit_code == 0
        assert result.stdout.strip() == str(Path.cwd())
        result = shell.run(
            ModuleContext(
                args={"cmd": "pwd"},
                env={},
                working_directory=tmp_path,
            )
        )
        assert result.stdout.strip() == str(tmp_path)

    def test_multiline_stdout(self):
        result = shell.run(
            _ctx({"cmd": 'echo "line1"; echo "line2"; echo "line3"'})
        )
        assert "line1" in result.stdout
        assert "line2" in result.stdout
        assert "line3" in result.stdout

    def test_missing_cmd_returns_error(self):
        result = shell.run(_ctx({}))
        assert result.exit_code == 1
        assert "requires 'cmd'" in result.stderr

    def test_nonexistent_shell_reports_error(self):
        result = shell.run(_ctx({"cmd": "echo hi", "shell": "/no/such/shell"}))
        assert result.exit_code == 1
        assert "Shell not found" in result.stderr


class TestShellOutputsFile:
    """$RUNNER_OUTPUTS capture (file NOT deleted by the builtin)."""

    def test_captures_key_value_lines(self, tmp_path):
        outputs_file = tmp_path / "outputs.txt"
        result = shell.run(
            _ctx(
                {
                    "cmd": (
                        'echo "name=Alice" >> $RUNNER_OUTPUTS\n'
                        'echo "age=30" >> $RUNNER_OUTPUTS\n'
                    )
                },
                env={"RUNNER_OUTPUTS": str(outputs_file)},
            )
        )
        assert result.exit_code == 0
        assert result.outputs["name"] == "Alice"
        assert result.outputs["age"] == "30"
        # The builtin must not delete the file; StepExecutor owns cleanup.
        assert outputs_file.exists()

    def test_malformed_lines_ignored(self, tmp_path):
        outputs_file = tmp_path / "outputs.txt"
        result = shell.run(
            _ctx(
                {
                    "cmd": (
                        'echo "valid_key=valid_value" >> $RUNNER_OUTPUTS\n'
                        'echo "malformed line without equals" >> $RUNNER_OUTPUTS\n'
                        'echo "another_key=another_value" >> $RUNNER_OUTPUTS\n'
                    )
                },
                env={"RUNNER_OUTPUTS": str(outputs_file)},
            )
        )
        assert result.outputs["valid_key"] == "valid_value"
        assert result.outputs["another_key"] == "another_value"
        assert "malformed line without equals" not in result.outputs

    def test_value_with_equals_sign(self, tmp_path):
        outputs_file = tmp_path / "outputs.txt"
        result = shell.run(
            _ctx(
                {"cmd": 'echo "equation=a=b+c" >> $RUNNER_OUTPUTS'},
                env={"RUNNER_OUTPUTS": str(outputs_file)},
            )
        )
        assert result.outputs["equation"] == "a=b+c"

    def test_value_with_spaces(self, tmp_path):
        outputs_file = tmp_path / "outputs.txt"
        result = shell.run(
            _ctx(
                {"cmd": 'echo "message=Hello World" >> $RUNNER_OUTPUTS'},
                env={"RUNNER_OUTPUTS": str(outputs_file)},
            )
        )
        assert result.outputs["message"] == "Hello World"

    def test_overwrite_previous(self, tmp_path):
        outputs_file = tmp_path / "outputs.txt"
        result = shell.run(
            _ctx(
                {
                    "cmd": (
                        'echo "counter=1" >> $RUNNER_OUTPUTS\n'
                        'echo "counter=2" >> $RUNNER_OUTPUTS\n'
                        'echo "counter=3" >> $RUNNER_OUTPUTS\n'
                    )
                },
                env={"RUNNER_OUTPUTS": str(outputs_file)},
            )
        )
        assert result.outputs["counter"] == "3"

    def test_empty_value_preserved(self, tmp_path):
        outputs_file = tmp_path / "outputs.txt"
        result = shell.run(
            _ctx(
                {
                    "cmd": (
                        'echo "empty_key=" >> $RUNNER_OUTPUTS\n'
                        'echo "has_value=something" >> $RUNNER_OUTPUTS\n'
                    )
                },
                env={"RUNNER_OUTPUTS": str(outputs_file)},
            )
        )
        assert result.outputs["empty_key"] == ""
        assert result.outputs["has_value"] == "something"


class TestShellTruncation:
    def test_large_stdout_truncated(self, monkeypatch):
        monkeypatch.setenv("OFX_MAX_OUTPUT_SIZE", "100")
        result = shell.run(_ctx({"cmd": "python3 -c \"print('x' * 200)\""}))
        assert result.outputs.get("output_truncated") is True
        assert "[OUTPUT TRUNCATED]" in result.stdout

    def test_large_stderr_truncated(self, monkeypatch):
        monkeypatch.setenv("OFX_MAX_OUTPUT_SIZE", "100")
        result = shell.run(_ctx({"cmd": "python3 -c \"import sys; sys.stderr.write('e' * 200)\""}))
        assert result.outputs.get("stderr_truncated") is True
        assert "[STDERR TRUNCATED]" in result.stderr

    def test_binary_output_base64(self):
        result = shell.run(_ctx({"cmd": "printf '\\377\\000\\001'"}))
        assert result.outputs.get("binary_output") is True
        assert result.stdout.startswith("AAEC") or result.stdout.startswith("/wAB")

    def test_normal_output_not_truncated(self):
        result = shell.run(_ctx({"cmd": "echo small"}))
        assert result.outputs.get("output_truncated") is None
        assert result.stdout.strip() == "small"


class TestShellStreaming:
    def test_streams_lines_to_ctx_log(self):
        lines: list[str] = []
        result = shell.run(
            _ctx({"cmd": 'printf "a1\\nb2\\nc3\\n"'}, logger=lines.append)
        )
        assert result.exit_code == 0
        assert result.stdout == "a1\nb2\nc3"
        assert lines == ["a1", "b2", "c3"]

    def test_stream_without_logger_still_captures(self):
        result = shell.run(_ctx({"cmd": 'printf "a1\\nb2\\n"'}))
        assert result.exit_code == 0
        assert result.stdout == "a1\nb2"

    def test_stream_captures_stderr(self):
        result = shell.run(
            _ctx({"cmd": 'echo out; echo err >&2'}, logger=lambda _m: None)
        )
        assert result.exit_code == 0
        assert "out" in result.stdout
        assert "err" in result.stderr


class TestShellInteractive:
    def test_interactive_requires_allow_env(self):
        """Interactive flag without OFX_ALLOW_INTERACTIVE falls back to capture."""
        result = shell.run(
            _ctx({"cmd": "echo captured"}, interactive=True, env={})
        )
        assert result.exit_code == 0
        assert result.stdout.strip() == "captured"

    def test_interactive_placeholder_stdout(self, monkeypatch):
        """Interactive mode with permission returns the real-time placeholder."""
        monkeypatch.setenv("OFX_ALLOW_INTERACTIVE", "true")
        result = shell.run(
            _ctx({"cmd": "echo hi"}, interactive=True, env={"OFX_ALLOW_INTERACTIVE": "true"})
        )
        assert result.exit_code == 0
        assert result.stdout == "[Interactive mode - output shown in real-time]"

    def test_interactive_timeout(self, monkeypatch):
        monkeypatch.setenv("OFX_ALLOW_INTERACTIVE", "true")
        result = shell.run(
            _ctx(
                {"cmd": "sleep 5", "timeout_minutes": 0.01},
                interactive=True,
                env={"OFX_ALLOW_INTERACTIVE": "true"},
            )
        )
        assert result.exit_code == 124
        assert "timed out after" in result.stderr


class TestShellTimeout:
    def test_timeout_returns_124_with_message(self):
        result = shell.run(_ctx({"cmd": "sleep 5", "timeout_minutes": 0.01}))
        assert result.exit_code == 124
        assert result.stderr == "Command timed out after 0.01 minutes"

    def test_timeout_kills_process_group(self):
        """Grandchildren in the process group are killed on timeout."""
        script = "sleep 30 & wait"
        result = shell.run(_ctx({"cmd": script, "timeout_minutes": 0.01}))
        assert result.exit_code == 124


class TestShellFunctionsPreamble:
    def test_preamble_includes_helper_exports(self):
        functions = shell.get_shell_functions("/bin/bash")
        assert "export TOOLS_DIR=" in functions
        assert "export RUNNER_PYTHON=" in functions
        assert "export CHANNELS_DIR=" in functions
        assert "fapt()" in functions
        assert "ch_publish()" in functions

    def test_preamble_honors_channels_dir(self):
        functions = shell.get_shell_functions("/bin/bash", channels_dir="/tmp/ofx-ch")
        assert 'export CHANNELS_DIR="/tmp/ofx-ch"' in functions

    def test_get_shell_exports_for_templates(self):
        exports = shell.get_shell_exports()
        assert "sudo" in exports
        assert "tools_dir" in exports
        assert "tools_bin_dir" in exports
        assert "temp_dir" in exports
        assert "python" in exports
        assert "is_windows" in exports


class TestShellViaModuleRunner:
    @pytest.mark.asyncio
    async def test_shell_builtin_captures_stdout(self):
        invocation = ModuleInvocation(name="shell", args={"cmd": "echo module-shell"})
        runner = ModuleRunner(invocation, RunContext())
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["stdout"].strip() == "module-shell"
        assert outputs["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_shell_builtin_nonzero_exit_fails(self):
        runner = ModuleRunner(
            ModuleInvocation(name="shell", args={"cmd": "exit 7"}), RunContext()
        )
        result = await runner.run()
        assert result.status == RunnerStatus.FAILED
        assert "exit code 7" in result.error

    @pytest.mark.asyncio
    async def test_shell_builtin_requires_cmd(self):
        runner = ModuleRunner(ModuleInvocation(name="shell", args={}), RunContext())
        result = await runner.run()
        assert result.status == RunnerStatus.FAILED
        assert "requires 'cmd'" in result.error

    @pytest.mark.asyncio
    async def test_step_timeout_reaches_builtin(self):
        """ModuleInvocation.timeout_minutes feeds the builtin's default."""
        runner = ModuleRunner(
            ModuleInvocation(name="shell", args={"cmd": "sleep 5"}, timeout_minutes=0),
            RunContext(),
        )
        result = await runner.run()
        assert result.status == RunnerStatus.FAILED
        assert "timed out" in result.error


def test_outputs_file_helper_helpers():
    """The parse helpers exist on the module (behavior contract)."""
    assert callable(shell.capture_outputs_file)
