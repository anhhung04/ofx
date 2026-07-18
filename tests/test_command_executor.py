"""Tests for CommandExecutor subprocess handling."""

from __future__ import annotations

import base64
import asyncio
import os
import signal
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ofx.models.command import Command
from ofx.runner.commands.command_executor import (
    CommandExecutionResult,
    CommandExecutor,
    _kill_process_tree,
    _process_group_id,
    parse_outputs_file,
    prepare_outputs_file_env,
)

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
        binary_data = bytes(range(256))
        stdout, stderr, outputs = executor._decode_output(binary_data, b"\x80\x81")
        assert outputs.get("binary_output") is True
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

class TestDecodeOutputHelpers:
    def test_parse_outputs_file_filters_invalid_entries_and_logs(self, tmp_path):
        path = tmp_path / "outputs.txt"
        path.write_text("a=1\nnope\n b = 2 ")
        messages: list[str] = []

        parsed = parse_outputs_file(path, messages.append)

        assert parsed == {"a": "1", "b": "2"}
        assert messages == ["Captured output: a=1", "Captured output: b=2"]

    def test_decode_output_handles_text_and_binary_streams(self):
        executor = _make_executor()

        stdout, stderr, outputs = executor._decode_output(b"hello", b"warn")

        assert stdout == "hello"
        assert stderr == "warn"
        assert outputs == {}

        stdout, stderr, outputs = executor._decode_output(b"\xff\x00", b"\x80")

        assert outputs["binary_output"] is True
        assert isinstance(stdout, str)
        assert isinstance(stderr, str)

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

class TestPrepareOutputsFileEnv:
    def test_sets_ofx_alias_when_requested(self):
        envs = dict(os.environ)

        outputs_file = prepare_outputs_file_env(
            envs,
            interactive=False,
            include_ofx_alias=True,
        )

        assert outputs_file is not None
        assert envs["RUNNER_OUTPUTS"] == str(outputs_file)
        assert envs["OFX_OUTPUTS"] == str(outputs_file)
        outputs_file.unlink(missing_ok=True)

    def test_reuses_existing_runner_outputs_for_ofx_alias(self):
        fd, tmp_path = tempfile.mkstemp(prefix=".test_out_", suffix=".txt")
        os.close(fd)
        try:
            envs = {**os.environ, "RUNNER_OUTPUTS": tmp_path}

            outputs_file = prepare_outputs_file_env(
                envs,
                interactive=False,
                include_ofx_alias=True,
            )

            assert outputs_file == Path(tmp_path)
            assert envs["OFX_OUTPUTS"] == tmp_path
        finally:
            Path(tmp_path).unlink(missing_ok=True)

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

    async def test_streaming_truncates_stdout_when_limit_exceeded(self, monkeypatch):
        monkeypatch.setattr(
            "ofx.runner.commands.command_executor.settings.max_output_size",
            3,
        )
        executor = _make_executor(cmd='printf "abcde\\n"')

        result = await executor.execute_streaming(on_line=lambda _: None)

        assert result.stdout.endswith("[OUTPUT TRUNCATED]")
        assert result.outputs == {"output_truncated": True}

class TestCommandExecutionHelpers:
    """Small helper tests for command construction."""

    @pytest.mark.asyncio
    async def test_execute_streaming_builds_result_from_fake_process(self, monkeypatch):
        executor = _make_executor()

        class _Stdout:
            def __init__(self, lines):
                self._lines = iter(lines)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._lines)
                except StopIteration as exc:
                    raise StopAsyncIteration from exc

        class _Stderr:
            async def read(self):
                return b"warn"

        class _Proc:
            returncode = 0
            stdout = _Stdout([b"one\n", b"two\n"])
            stderr = _Stderr()

            async def wait(self):
                return 0

        async def _spawn_subprocess(**_kwargs):
            return _Proc()

        async def _await_with_timeout(_proc, awaitable):
            return await awaitable

        monkeypatch.setattr(executor, "_spawn_subprocess", _spawn_subprocess)
        monkeypatch.setattr(executor, "_await_with_timeout", _await_with_timeout)

        result = await executor.execute_streaming(on_line=None)

        assert result == CommandExecutionResult(
            exit_code=0,
            stdout="one\ntwo",
            stderr="warn",
            outputs={},
        )

    @pytest.mark.asyncio
    async def test_execute_streaming_base64_encodes_binary_stderr_with_fake_process(self, monkeypatch):
        executor = _make_executor()

        class _Stdout:
            def __init__(self, lines):
                self._lines = iter(lines)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._lines)
                except StopIteration as exc:
                    raise StopAsyncIteration from exc

        class _Stderr:
            async def read(self):
                return b"\x80\x81"

        class _Proc:
            returncode = 0
            stdout = _Stdout([b"one\n"])
            stderr = _Stderr()

            async def wait(self):
                return 0

        async def _spawn_subprocess(**_kwargs):
            return _Proc()

        async def _await_with_timeout(_proc, awaitable):
            return await awaitable

        monkeypatch.setattr(executor, "_spawn_subprocess", _spawn_subprocess)
        monkeypatch.setattr(executor, "_await_with_timeout", _await_with_timeout)

        result = await executor.execute_streaming(on_line=None)

        assert result.stderr == base64.b64encode(b"\x80\x81").decode("utf-8")

    @pytest.mark.asyncio
    async def test_execute_streaming_marks_truncated_output_with_fake_process(self, monkeypatch):
        executor = _make_executor()

        class _Stdout:
            def __init__(self, lines):
                self._lines = iter(lines)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._lines)
                except StopIteration as exc:
                    raise StopAsyncIteration from exc

        class _Stderr:
            async def read(self):
                return b""

        class _Proc:
            returncode = 0
            stdout = _Stdout([b"abcde\n"])
            stderr = _Stderr()

            async def wait(self):
                return 0

        async def _spawn_subprocess(**_kwargs):
            return _Proc()

        async def _await_with_timeout(_proc, awaitable):
            return await awaitable

        monkeypatch.setattr(executor, "_spawn_subprocess", _spawn_subprocess)
        monkeypatch.setattr(executor, "_await_with_timeout", _await_with_timeout)
        monkeypatch.setattr(
            "ofx.runner.commands.command_executor.settings.max_output_size",
            3,
        )

        result = await executor.execute_streaming(on_line=None)

        assert result.stdout.endswith("[OUTPUT TRUNCATED]")
        assert result.outputs == {"output_truncated": True}

    @pytest.mark.asyncio
    async def test_spawn_subprocess_uses_command_config(self, monkeypatch):
        executor = _make_executor(timeout_minutes=2, working_directory=Path("/tmp"))
        captured = {}

        async def _create_subprocess_shell(command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            return object()

        monkeypatch.setattr(
            "asyncio.create_subprocess_shell",
            _create_subprocess_shell,
        )

        await executor._spawn_subprocess(stdout="pipe")

        assert captured["command"].endswith("\necho hello")
        assert len(captured["command"]) > len("echo hello")
        kwargs = captured["kwargs"]
        assert kwargs["executable"] == "/bin/bash"
        assert kwargs["cwd"] == Path("/tmp")
        assert kwargs["env"] == executor._envs
        assert kwargs["start_new_session"] is True
        assert kwargs["stdout"] == "pipe"

    @pytest.mark.asyncio
    async def test_run_non_interactive_builds_result_from_process_outputs(self, monkeypatch):
        executor = _make_executor()

        class _Proc:
            returncode = 0

            async def communicate(self):
                return b"ok", b"warn"

        async def _spawn_subprocess(**_kwargs):
            return _Proc()

        async def _await_with_timeout(_proc, awaitable):
            return await awaitable

        monkeypatch.setattr(executor, "_spawn_subprocess", _spawn_subprocess)
        monkeypatch.setattr(executor, "_await_with_timeout", _await_with_timeout)

        result = await executor._run_non_interactive()

        assert result == CommandExecutionResult(
            exit_code=0,
            stdout="ok",
            stderr="warn",
            outputs={},
        )

    @pytest.mark.asyncio
    async def test_run_interactive_builds_placeholder_result(self, monkeypatch):
        executor = _make_executor(interactive=True)

        class _Proc:
            async def wait(self):
                return 130

        async def _spawn_subprocess(**_kwargs):
            return _Proc()

        async def _await_with_timeout(_proc, awaitable):
            return await awaitable

        monkeypatch.setattr(executor, "_spawn_subprocess", _spawn_subprocess)
        monkeypatch.setattr(executor, "_await_with_timeout", _await_with_timeout)

        result = await executor._run_interactive()

        assert result == CommandExecutionResult(
            exit_code=130,
            stdout="[Interactive mode - output shown in real-time]",
            stderr="",
            outputs={},
        )

    def test_kill_process_tree_waits_then_stops_when_group_exits(self, monkeypatch):
        proc = SimpleNamespace(pid=123)
        signals: list[tuple[int, object]] = []
        polls = iter([None, ProcessLookupError()])

        monkeypatch.setattr(
            "ofx.runner.commands.command_executor.os.getpgid",
            lambda pid: pid + 1,
        )

        def _killpg(pgid, sig):
            if sig != 0:
                signals.append((pgid, sig))
                return
            result = next(polls)
            if isinstance(result, BaseException):
                raise result

        monotonic_values = iter([0.0, 0.1, 0.2])
        monkeypatch.setattr("ofx.runner.commands.command_executor.os.killpg", _killpg)
        monkeypatch.setattr("time.sleep", lambda _seconds: None)
        monkeypatch.setattr("time.monotonic", lambda: next(monotonic_values))

        _kill_process_tree(proc)

        assert signals == [(124, signal.SIGTERM)]

    def test_process_group_id_returns_none_for_missing_or_unresolvable_process(self, monkeypatch):
        assert _process_group_id(SimpleNamespace(pid=None)) is None

        monkeypatch.setattr(
            "ofx.runner.commands.command_executor.os.getpgid",
            lambda _pid: (_ for _ in ()).throw(ProcessLookupError()),
        )

        assert _process_group_id(SimpleNamespace(pid=123)) is None

    @pytest.mark.asyncio
    async def test_await_with_timeout_signals_group_and_closes_transport(self, monkeypatch):
        calls: list[tuple[str, object]] = []

        class _Transport:
            def close(self):
                calls.append(("close", None))

        proc = SimpleNamespace(pid=123, _transport=_Transport())

        monkeypatch.setattr(
            "ofx.runner.commands.command_executor.os.getpgid",
            lambda pid: pid + 1,
        )
        monkeypatch.setattr(
            "ofx.runner.commands.command_executor.os.killpg",
            lambda pgid, sig: calls.append(("kill", (pgid, sig))),
        )

        executor = _make_executor(timeout_minutes=1)

        result = await executor._await_with_timeout(proc, asyncio.sleep(0, result="ok"))

        assert result == "ok"
        assert calls == [
            ("kill", (124, signal.SIGTERM)),
            ("close", None),
        ]

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
        assert not Path(tmp_path).exists()

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

    async def test_capture_outputs_file_updates_registry_once(self):
        fd, tmp_path = tempfile.mkstemp(prefix=".test_cap_", suffix=".txt")
        os.close(fd)
        Path(tmp_path).write_text("a=1\nb=2\n")

        calls: list[tuple[str, dict[str, str]]] = []
        runner = MagicMock()
        executor = _make_executor()
        executor._outputs_file = Path(tmp_path)

        async def _reg_update(key, data):
            calls.append((key, dict(data)))

        runner.reg_update = _reg_update

        await executor.capture_outputs_file(runner, "outputs", lambda _message: None)

        assert calls == [("outputs", {"a": "1", "b": "2"})]

class TestTimeout:
    """Timeout handling tests."""

    async def test_command_timeout_raises(self):
        executor = _make_executor(cmd="sleep 10", timeout_minutes=1)
        object.__setattr__(executor._command, "timeout_minutes", 0.01)
        with pytest.raises(RuntimeError, match="timed out"):
            await executor.execute()

    async def test_streaming_timeout_raises(self):
        executor = _make_executor(cmd="sleep 10", timeout_minutes=1)
        object.__setattr__(executor._command, "timeout_minutes", 0.01)
        with pytest.raises(RuntimeError, match="timed out"):
            await executor.execute_streaming(on_line=lambda _: None)

    async def test_await_with_timeout_kills_and_waits_on_timeout(self):
        executor = _make_executor(timeout_minutes=1)
        object.__setattr__(executor._command, "timeout_minutes", 0)
        proc = MagicMock()
        proc.wait = AsyncMock()

        with patch("ofx.runner.commands.command_executor._kill_process_tree") as mock_kill:
            with pytest.raises(RuntimeError, match="timed out"):
                await executor._await_with_timeout(proc, asyncio.sleep(0.01))

        mock_kill.assert_called_once_with(proc)
        proc.wait.assert_awaited_once()
