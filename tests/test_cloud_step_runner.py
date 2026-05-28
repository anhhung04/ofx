"""Tests for CloudStepRunner remote dispatch helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ofx.models.step import RunType, Step
from ofx.runner import RunContext
from ofx.runner.cloud_step import CloudStepRunner


@pytest.mark.asyncio
async def test_execute_remote_run_type_dispatches_supported_modes():
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(task="httpx", run_with={"target": "example.com"})

    calls: list[tuple[str, object, int]] = []

    async def _run_remote_command(command, timeout=None):
        calls.append(("command", command, timeout))
        return "command-output"

    async def _run_remote_python_step(timeout=None):
        calls.append(("python_step", None, timeout))
        return "python-step-output"

    async def _run_remote_task(timeout=None):
        calls.append(("task", None, timeout))
        return "task-output"

    runner._run_remote_command = _run_remote_command
    runner._run_remote_python_step = _run_remote_python_step
    runner._run_remote_task = _run_remote_task

    runner.model = Step(run="echo hi")
    assert await runner._execute_remote_run_type(RunType.COMMAND, timeout_seconds=10) == "command-output"

    runner.model = Step(script="print('hi')")
    assert await runner._execute_remote_run_type(RunType.SCRIPT, timeout_seconds=11) == "python-step-output"

    runner.model = Step(script_file="worker.py")
    assert await runner._execute_remote_run_type(RunType.SCRIPT_FILE, timeout_seconds=12) == "python-step-output"

    runner.model = Step(task="httpx", run_with={"target": "example.com"})
    assert await runner._execute_remote_run_type(RunType.TASK, timeout_seconds=13) == "task-output"

    assert calls == [
        ("command", "echo hi", 10),
        ("python_step", None, 11),
        ("python_step", None, 12),
        ("task", None, 13),
    ]


def test_unsupported_remote_run_type_error_messages():
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(uses="./child.yml")

    workflow_error = runner._unsupported_remote_run_type_error(RunType.WORKFLOW)
    assert "Reusable workflows" in str(workflow_error)

    pipe_runner = object.__new__(CloudStepRunner)
    pipe_runner.model = Step(pipe={"input": "x"})
    pipe_error = pipe_runner._unsupported_remote_run_type_error(RunType.PIPE)
    assert "Pipe steps run locally" in str(pipe_error)


def test_remote_outputs_include_typed_outputs_only_for_task_steps():
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(task="httpx", run_with={"target": "example.com"})
    runner._parse_task_output = lambda stdout: [{"parsed": stdout}]

    task_outputs = runner._remote_outputs(RunType.TASK, "task-stdout")
    assert task_outputs == {
        "stdout": "task-stdout",
        "typed_outputs": [{"parsed": "task-stdout"}],
    }

    runner.model = Step(run="echo hi")
    command_outputs = runner._remote_outputs(RunType.COMMAND, "cmd-stdout")
    assert command_outputs == {"stdout": "cmd-stdout"}


@pytest.mark.asyncio
async def test_pre_run_sets_remote_work_dir_and_resolves_non_workflow_fields():
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(run="echo hi")
    runner.ctx = RunContext()
    runner.parent = SimpleNamespace(_cloud_config=SimpleNamespace(connection_type="ssh"))
    runner._state_machine = SimpleNamespace(transition=lambda _status: None)
    runner._apply_retry_profile_defaults = lambda: None
    runner._resolve_remote_work_dir = lambda: "/tmp/ofx-run"
    runner._resolve_template_fields = AsyncMock(return_value=None)
    runner._resolve_timeout_field = AsyncMock(return_value=None)
    runner._evaluate_run_if = lambda _expr, _context=None: True
    runner._run_if_context = lambda: {}

    await runner._pre_run()

    assert runner._run_type == RunType.COMMAND
    assert runner.ctx.vars["remote_work_dir"] == "/tmp/ofx-run"
    runner._resolve_template_fields.assert_awaited_once_with(
        [
            "name",
            "shell",
            "working_directory",
            "log_stdout",
            "log_command",
            "env",
            "run_if",
            "run",
        ]
    )
    runner._resolve_timeout_field.assert_awaited_once()


def test_build_remote_exec_command_uses_unix_shell_conventions():
    runner = object.__new__(CloudStepRunner)
    runner.parent = SimpleNamespace(_cloud_config=SimpleNamespace(connection_type="ssh"))
    runner._build_env_prefix = lambda: "export FOO=bar;"
    runner._resolve_remote_work_dir = lambda: "/tmp/ofx run"

    command = runner._build_remote_exec_command("echo hi")

    assert command == "export FOO=bar; cd '/tmp/ofx run' && echo hi"


def test_build_remote_exec_command_uses_windows_shell_conventions():
    from ofx.runner.cloud_job import CloudJobRunner

    runner = object.__new__(CloudStepRunner)
    runner.parent = object.__new__(CloudJobRunner)
    runner.parent._cloud_config = SimpleNamespace(connection_type="winrm")
    runner._build_env_prefix = lambda: "SET FOO=bar"
    runner._resolve_remote_work_dir = lambda: "C:\\ofx"

    command = runner._build_remote_exec_command("echo hi")

    assert command == 'SET FOO=bar && cd /d "C:\\ofx" && echo hi'


@pytest.mark.asyncio
async def test_run_remote_python_step_uses_cloud_opsec_mode(monkeypatch, tmp_path):
    captured = {}

    def _fake_build_python_step_payload(step, *, workflow_dir=None, opsec_mode=False, obfuscate_sources=False):
        captured["step"] = step
        captured["workflow_dir"] = workflow_dir
        captured["opsec_mode"] = opsec_mode
        captured["obfuscate_sources"] = obfuscate_sources
        return "payload"

    monkeypatch.setattr(
        "ofx.runner.cloud_step.build_python_step_payload",
        _fake_build_python_step_payload,
    )

    runner = object.__new__(CloudStepRunner)
    runner.model = Step(script="print('hi')")
    runner.ctx = SimpleNamespace(workflow_dir=tmp_path)
    runner.parent = SimpleNamespace(_cloud_config=SimpleNamespace(opsec_mode=True))
    runner._run_remote_python_payload = lambda payload, timeout=None: pytest.fail("payload execution should be awaited")

    async def _run_remote_python_payload(payload, timeout=None):
        captured["payload"] = payload
        captured["timeout"] = timeout
        return "ok"

    runner._run_remote_python_payload = _run_remote_python_payload

    result = await runner._run_remote_python_step(timeout=21)

    assert result == "ok"
    assert captured == {
        "step": runner.model,
        "workflow_dir": tmp_path,
        "opsec_mode": True,
        "obfuscate_sources": True,
        "payload": "payload",
        "timeout": 21,
    }


@pytest.mark.asyncio
async def test_run_remote_python_step_resolves_source_before_upload(monkeypatch, tmp_path):
    captured = {}

    def _fake_build_python_step_payload(step, *, workflow_dir=None, opsec_mode=False, obfuscate_sources=False):
        captured["step"] = step
        captured["workflow_dir"] = workflow_dir
        captured["opsec_mode"] = opsec_mode
        captured["obfuscate_sources"] = obfuscate_sources
        return "payload:resolved"

    monkeypatch.setattr(
        "ofx.runner.cloud_step.build_python_step_payload",
        _fake_build_python_step_payload,
    )

    runner = object.__new__(CloudStepRunner)
    runner.model = Step(script_file="worker")
    runner.ctx = SimpleNamespace(workflow_dir=tmp_path)
    runner.parent = SimpleNamespace(_cloud_config=SimpleNamespace(opsec_mode=False))

    async def _run_remote_python_payload(payload, *, timeout=None):
        captured["payload"] = payload
        captured["timeout"] = timeout
        return "ok"

    runner._run_remote_python_payload = _run_remote_python_payload

    result = await runner._run_remote_python_step(timeout=21)

    assert result == "ok"
    assert captured == {
        "step": runner.model,
        "workflow_dir": tmp_path,
        "opsec_mode": False,
        "obfuscate_sources": False,
        "payload": "payload:resolved",
        "timeout": 21,
    }


@pytest.mark.asyncio
async def test_run_remote_python_payload_uploads_executes_and_cleans_up(monkeypatch):
    from ofx.runner.cloud_job import CloudJobRunner

    uploads = []
    commands = []

    class _Remote:
        def upload(self, local_path, remote_path):
            uploads.append((local_path, remote_path))

        def run(self, command, timeout=None):
            commands.append((command, timeout))
            return "ok"

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", _fake_to_thread)

    runner = object.__new__(CloudStepRunner)
    runner._remote = _Remote()
    runner._work_dir = "/tmp/ofx-run"
    runner.parent = object.__new__(CloudJobRunner)
    runner.parent._cloud_config = SimpleNamespace(connection_type="ssh")
    runner._build_env_prefix = lambda: "export FOO=bar;"
    runner._resolve_remote_work_dir = lambda: "/tmp/ofx-run"

    async def _discover_python():
        return "python3"

    runner._discover_python = _discover_python
    runner._log_debug = lambda _message: None

    result = await runner._run_remote_python_payload("print('hi')", timeout=30)

    assert result == "ok"
    assert len(uploads) == 1
    local_path, remote_path = uploads[0]
    assert remote_path.startswith("/tmp/ofx-run/")
    assert remote_path.endswith(".py")
    assert commands[0][1] == 30
    assert "python3" in commands[0][0]
    assert remote_path in commands[0][0]
    assert commands[1] == (f"rm -f {remote_path}", 10)


@pytest.mark.asyncio
async def test_run_remote_python_payload_uses_windows_paths(monkeypatch):
    from ofx.runner.cloud_job import CloudJobRunner

    uploads = []
    commands = []

    class _Remote:
        def upload(self, local_path, remote_path):
            uploads.append((local_path, remote_path))

        def run(self, command, timeout=None):
            commands.append((command, timeout))
            return "ok"

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("asyncio.to_thread", _fake_to_thread)

    runner = object.__new__(CloudStepRunner)
    runner._remote = _Remote()
    runner._work_dir = "C:\\ofx"
    runner.parent = object.__new__(CloudJobRunner)
    runner.parent._cloud_config = SimpleNamespace(connection_type="winrm")
    runner._build_env_prefix = lambda: "SET FOO=bar"
    runner._resolve_remote_work_dir = lambda: "C:\\ofx"

    async def _discover_python():
        return "python.exe"

    runner._discover_python = _discover_python
    runner._log_debug = lambda _message: None

    result = await runner._run_remote_python_payload("print('hi')", timeout=30)

    assert result == "ok"
    assert len(uploads) == 1
    _local_path, remote_path = uploads[0]
    assert remote_path.startswith("C:\\ofx\\")
    assert remote_path.endswith(".py")
    assert commands[0][1] == 30
    assert 'cd /d "C:\\ofx"' in commands[0][0]
    assert f'"python.exe" "{remote_path}"' in commands[0][0]
    assert commands[1] == (f'del /f "{remote_path}"', 10)
