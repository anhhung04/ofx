"""Tests for CommandExecutor subprocess handling."""

from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ofx.models.command import Command
from ofx.runner.commands.command_executor import CommandExecutionResult, CommandExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executor(
    cmd: str = "echo hello",
    shell: str = "/bin/bash",
    timeout_minutes: float = 1,
    interactive: bool = False,
    envs: dict[str, Any] | None = None,
    working_directory: Path | None = None,
) -> CommandExecutor:
    kwargs: dict[str, Any] = {
        "cmd": cmd,
        "shell": shell,
        "timeout_minutes": timeout_minutes,
        "interactive": interactive,
    }
    if working_directory is not None:
        kwargs["working_directory"] = working_directory
    command = Command(**kwargs)
    return CommandExecutor(command, envs=dict(os.environ, **(envs or {})))


# ===================================================================
# 1. TestDecodeOutput
# ===================================================================


class TestDecodeOutput:
    """Test _decode_output directly."""

    def test_normal_utf8(self):
        executor = _make_executor()
        stdout, stderr, outputs = executor._decode_output(
            b"hello world", b"some warning"
        )
        assert stdout == "hello world"
        assert stderr == "some warning"
        assert outputs == {}

    @patch("ofx.runner.commands.command_executor.settings")
    def test_large_stdout_truncated(self, mock_settings):
        mock_settings.max_output_size = 100
        executor = _make_executor()
        large = b"A" * 200
        stdout, stderr, outputs = executor._decode_output(large, b"")
        assert "OUTPUT TRUNCATED" in stdout
        assert outputs.get("output_truncated") is True
        # Truncated content should start with the first 100 bytes
        assert stdout.startswith("A" * 100)

    @patch("ofx.runner.commands.command_executor.settings")
    def test_large_stderr_truncated(self, mock_settings):
        mock_settings.max_output_size = 100
        executor = _make_executor()
        large_err = b"E" * 200
        stdout, stderr, outputs = executor._decode_output(b"ok", large_err)
        assert "STDERR TRUNCATED" in stderr
        assert outputs.get("stderr_truncated") is True

    @patch("ofx.runner.commands.command_executor.settings")
    def test_both_truncated(self, mock_settings):
        mock_settings.max_output_size = 50
        executor = _make_executor()
        stdout, stderr, outputs = executor._decode_output(b"X" * 200, b"Y" * 200)
        assert outputs.get("output_truncated") is True
        assert outputs.get("stderr_truncated") is True

    def test_binary_output_base64(self):
        executor = _make_executor()
        # Bytes that cannot be decoded as UTF-8
        binary_data = bytes(range(256))
        stdout, stderr, outputs = executor._decode_output(binary_data, b"\x80\x81")
        assert outputs.get("binary_output") is True
        # Verify the base64 is decodable back
        assert base64.b64encode(binary_data).decode("utf-8") == stdout

    @patch("ofx.runner.commands.command_executor.settings")
    def test_binary_output_truncated(self, mock_settings):
        mock_settings.max_output_size = 50
        executor = _make_executor()
        binary_data = bytes(range(256))
        stdout, stderr, outputs = executor._decode_output(binary_data, b"\x80")
        assert outputs.get("binary_output") is True
        assert outputs.get("output_truncated") is True
        assert "BINARY OUTPUT TRUNCATED" in stdout


# ===================================================================
# 2. TestRaiseForStatus
# ===================================================================


class TestRaiseForStatus:
    """Test error handling via raise_for_status."""

    def test_exit_zero_does_not_raise(self):
        executor = _make_executor()
        executor.raise_for_status(0, "")

    def test_exit_nonzero_raises(self):
        executor = _make_executor()
        with pytest.raises(RuntimeError, match="Command failed"):
            executor.raise_for_status(1, "something broke")

    def test_exit_nonzero_uses_default_message(self):
        executor = _make_executor()
        with pytest.raises(RuntimeError, match="exit code 1"):
            executor.raise_for_status(1, "")

    def test_interactive_130_does_not_raise(self):
        executor = _make_executor(interactive=True)
        executor.raise_for_status(130, "")

    def test_interactive_127_does_not_raise(self):
        executor = _make_executor(interactive=True)
        executor.raise_for_status(127, "")

    def test_interactive_zero_does_not_raise(self):
        executor = _make_executor(interactive=True)
        executor.raise_for_status(0, "")

    def test_interactive_other_code_raises(self):
        executor = _make_executor(interactive=True)
        with pytest.raises(RuntimeError, match="Command failed"):
            executor.raise_for_status(2, "bad usage")


# ===================================================================
# 3. TestPrepareOutputsFile
# ===================================================================


class TestPrepareOutputsFile:
    """Test temp file creation for step outputs."""

    def test_creates_file_when_not_interactive(self):
        envs = dict(os.environ)
        executor = CommandExecutor(
            Command(cmd="echo hi", shell="/bin/bash", timeout_minutes=1),
            envs=envs,
        )
        executor.prepare_outputs_file()
        assert executor.outputs_file is not None
        assert executor.outputs_file.exists()
        assert "RUNNER_OUTPUTS" in envs
        # Cleanup
        executor.outputs_file.unlink(missing_ok=True)

    def test_reuses_existing_runner_outputs(self):
        fd, tmp_path = tempfile.mkstemp(prefix=".test_out_", suffix=".txt")
        os.close(fd)
        try:
            envs = {**os.environ, "RUNNER_OUTPUTS": tmp_path}
            executor = CommandExecutor(
                Command(cmd="echo hi", shell="/bin/bash", timeout_minutes=1),
                envs=envs,
            )
            executor.prepare_outputs_file()
            assert executor.outputs_file == Path(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_does_not_create_when_interactive(self):
        envs = dict(os.environ)
        executor = CommandExecutor(
            Command(
                cmd="echo hi",
                shell="/bin/bash",
                timeout_minutes=1,
                interactive=True,
            ),
            envs=envs,
        )
        executor.prepare_outputs_file()
        assert executor.outputs_file is None


# ===================================================================
# 4. TestExecuteCommand (async integration)
# ===================================================================


class TestExecuteCommand:
    """Integration tests running real subprocesses."""

    async def test_echo_captures_stdout(self):
        executor = _make_executor(cmd="echo hello")
        result = await executor.execute()
        assert result.exit_code == 0
        assert "hello" in result.stdout

    async def test_stderr_captured(self):
        executor = _make_executor(cmd="echo oops >&2")
        result = await executor.execute()
        assert result.exit_code == 0
        assert "oops" in result.stderr

    async def test_nonzero_exit_code(self):
        executor = _make_executor(cmd="exit 42")
        result = await executor.execute()
        assert result.exit_code == 42

    async def test_env_vars_passed(self):
        executor = _make_executor(
            cmd="echo $MY_TEST_VAR",
            envs={"MY_TEST_VAR": "testvalue123"},
        )
        result = await executor.execute()
        assert "testvalue123" in result.stdout

    async def test_working_directory_respected(self):
        executor = _make_executor(cmd="pwd", working_directory=Path("/tmp"))
        result = await executor.execute()
        # /tmp may be a symlink to /private/tmp on macOS, so just check the base
        assert result.stdout.strip().endswith("/tmp")

    async def test_multiline_stdout(self):
        executor = _make_executor(cmd='echo "line1"; echo "line2"; echo "line3"')
        result = await executor.execute()
        assert "line1" in result.stdout
        assert "line2" in result.stdout
        assert "line3" in result.stdout

    async def test_result_is_dataclass(self):
        executor = _make_executor(cmd="echo hi")
        result = await executor.execute()
        assert isinstance(result, CommandExecutionResult)
        assert isinstance(result.outputs, dict)


# ===================================================================
# 5. TestExecuteStreaming (async)
# ===================================================================


class TestExecuteStreaming:
    """Streaming execution tests."""

    async def test_lines_passed_to_callback(self):
        received: list[str] = []
        executor = _make_executor(cmd='echo "alpha"; echo "beta"; echo "gamma"')
        await executor.execute_streaming(on_line=received.append)
        assert "alpha" in received
        assert "beta" in received
        assert "gamma" in received

    async def test_full_stdout_collected(self):
        received: list[str] = []
        executor = _make_executor(cmd='echo "one"; echo "two"')
        result = await executor.execute_streaming(on_line=received.append)
        assert "one" in result.stdout
        assert "two" in result.stdout
        assert result.exit_code == 0

    async def test_callback_exception_does_not_crash(self):
        def bad_callback(line: str):
            raise ValueError("boom")

        executor = _make_executor(cmd='echo "safe"')
        result = await executor.execute_streaming(on_line=bad_callback)
        assert result.exit_code == 0
        assert "safe" in result.stdout

    async def test_none_callback(self):
        executor = _make_executor(cmd="echo ok")
        result = await executor.execute_streaming(on_line=None)
        assert result.exit_code == 0
        assert "ok" in result.stdout

    async def test_stderr_in_streaming(self):
        executor = _make_executor(cmd='echo "out"; echo "err" >&2')
        result = await executor.execute_streaming(on_line=lambda _: None)
        assert "out" in result.stdout
        assert "err" in result.stderr


# ===================================================================
# 6. TestCaptureOutputsFile (async)
# ===================================================================


class TestCaptureOutputsFile:
    """Output file parsing tests."""

    async def test_parses_key_value_lines(self):
        fd, tmp_path = tempfile.mkstemp(prefix=".test_cap_", suffix=".txt")
        os.close(fd)
        Path(tmp_path).write_text("name=alice\nage=30\n")

        executor = _make_executor()
        executor._outputs_file = Path(tmp_path)

        captured: dict[str, str] = {}
        runner = MagicMock()

        async def fake_reg_update(key, data):
            captured.update(data)

        runner.reg_update = fake_reg_update
        logs: list[str] = []

        await executor.capture_outputs_file(runner, "step_key", logs.append)

        assert captured == {"name": "alice", "age": "30"}
        assert not Path(tmp_path).exists()  # cleaned up

    async def test_handles_empty_file(self):
        fd, tmp_path = tempfile.mkstemp(prefix=".test_cap_", suffix=".txt")
        os.close(fd)
        Path(tmp_path).write_text("")

        executor = _make_executor()
        executor._outputs_file = Path(tmp_path)

        runner = MagicMock()
        runner.reg_update = AsyncMock()
        logs: list[str] = []

        await executor.capture_outputs_file(runner, "step_key", logs.append)

        runner.reg_update.assert_not_called()
        assert not Path(tmp_path).exists()

    async def test_handles_missing_file(self):
        executor = _make_executor()
        executor._outputs_file = Path("/tmp/.nonexistent_outputs_file_xyz.txt")

        runner = MagicMock()
        runner.reg_update = AsyncMock()
        logs: list[str] = []

        # Should not raise
        await executor.capture_outputs_file(runner, "step_key", logs.append)
        runner.reg_update.assert_not_called()

    async def test_handles_none_outputs_file(self):
        executor = _make_executor()
        assert executor.outputs_file is None

        runner = MagicMock()
        runner.reg_update = AsyncMock()

        await executor.capture_outputs_file(runner, "step_key", lambda m: None)
        runner.reg_update.assert_not_called()

    async def test_file_cleaned_up_after_parsing(self):
        fd, tmp_path = tempfile.mkstemp(prefix=".test_cap_", suffix=".txt")
        os.close(fd)
        Path(tmp_path).write_text("k=v\n")

        executor = _make_executor()
        executor._outputs_file = Path(tmp_path)

        runner = MagicMock()

        async def fake_reg_update(key, data):
            pass

        runner.reg_update = fake_reg_update

        await executor.capture_outputs_file(runner, "key", lambda m: None)
        assert not Path(tmp_path).exists()

    async def test_value_with_equals_sign(self):
        fd, tmp_path = tempfile.mkstemp(prefix=".test_cap_", suffix=".txt")
        os.close(fd)
        Path(tmp_path).write_text("url=https://example.com?foo=bar\n")

        executor = _make_executor()
        executor._outputs_file = Path(tmp_path)

        captured: dict[str, str] = {}
        runner = MagicMock()

        async def fake_reg_update(key, data):
            captured.update(data)

        runner.reg_update = fake_reg_update

        await executor.capture_outputs_file(runner, "key", lambda m: None)
        assert captured["url"] == "https://example.com?foo=bar"


# ===================================================================
# 7. TestTimeout (async)
# ===================================================================


class TestTimeout:
    """Timeout handling tests."""

    async def test_command_timeout_raises(self):
        # sleep 10 with a tiny timeout should trigger RuntimeError
        executor = _make_executor(cmd="sleep 10", timeout_minutes=1)
        # Bypass Pydantic validation to set a fractional minute timeout
        object.__setattr__(executor._command, "timeout_minutes", 0.01)
        with pytest.raises(RuntimeError, match="timed out"):
            await executor.execute()

    async def test_streaming_timeout_raises(self):
        executor = _make_executor(cmd="sleep 10", timeout_minutes=1)
        object.__setattr__(executor._command, "timeout_minutes", 0.01)
        with pytest.raises(RuntimeError, match="timed out"):
            await executor.execute_streaming(on_line=lambda _: None)
