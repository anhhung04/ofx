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
    runner.ctx = RunContext(vars={})
    runner.parent = SimpleNamespace(_cloud_config=SimpleNamespace(opsec_mode=False))
    runner._build_remote_exec_command = lambda command: f"wrapped:{command}"

    calls: list[tuple[str, object, int]] = []

    runner._remote = SimpleNamespace(
        run=lambda command, timeout=None: calls.append(("command", command, timeout)) or "command-output"
    )

    async def _run_remote_python_payload(payload, *, timeout=None):
        calls.append(("python_payload", payload, timeout))
        return "python-step-output"

    runner._run_remote_python_payload = _run_remote_python_payload

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("asyncio.to_thread", _fake_to_thread)

        runner.model = Step(run="echo hi")
        assert await runner._execute_remote_run_type(RunType.COMMAND, timeout_seconds=10) == "command-output"

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(
                "ofx.runner.cloud_step.build_python_step_payload",
                lambda model, **_kwargs: f"payload:{model.get_run_type().value}",
            )

            runner.model = Step(script="print('hi')")
            assert await runner._execute_remote_run_type(RunType.SCRIPT, timeout_seconds=11) == "python-step-output"

            runner.model = Step(script_file="worker.py")
            assert await runner._execute_remote_run_type(RunType.SCRIPT_FILE, timeout_seconds=12) == "python-step-output"

        runner.model = Step(task="httpx", run_with={"target": "example.com"})
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(
                "ofx.runner.cloud_step.build_task_command_from_step",
                lambda model, profile=None: "task-command",
            )
            assert await runner._execute_remote_run_type(RunType.TASK, timeout_seconds=13) == "command-output"

    assert calls == [
        ("command", "wrapped:echo hi", 10),
        ("python_payload", "payload:script", 11),
        ("python_payload", "payload:script_file", 12),
        ("command", "wrapped:task-command", 13),
    ]


@pytest.mark.asyncio
async def test_remote_handler_runner_delegates_run_type_timeout_and_output_storage():
    from ofx.runner.cloud_step import _RemoteHandlerRunner

    runner = object.__new__(CloudStepRunner)
    runner.model = Step(run="echo hi", timeout=2)
    runner._run_type = None

    stored: list[tuple[object, object]] = []

    async def _execute_remote_run_type(run_type, *, timeout_seconds):
        assert run_type == RunType.COMMAND
        assert timeout_seconds == 120
        return "command-output"

    async def _reg_set(key, value):
        stored.append((key, value))

    async def _get_result():
        return "result"

    runner._execute_remote_run_type = _execute_remote_run_type
    runner.reg_set = _reg_set
    runner.get_result = _get_result

    handler = _RemoteHandlerRunner(runner)

    assert await handler.run() == "result"
    assert stored == [(
        "outputs",
        {"stdout": "command-output"},
    )]


@pytest.mark.asyncio
async def test_execute_remote_run_type_rejects_workflow_and_pipe_steps():
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(uses="./child.yml")

    with pytest.raises(RuntimeError, match="Reusable workflows"):
        await runner._execute_remote_run_type(RunType.WORKFLOW, timeout_seconds=10)

    pipe_runner = object.__new__(CloudStepRunner)
    pipe_runner.model = Step(pipe={"input": "x"})
    with pytest.raises(RuntimeError, match="Pipe steps run locally"):
        await pipe_runner._execute_remote_run_type(RunType.PIPE, timeout_seconds=10)


@pytest.mark.asyncio
async def test_execute_remote_run_type_rejects_unknown_run_type_value():
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(name="scan-step", run="echo hi")

    with pytest.raises(RuntimeError, match="Unsupported run type 'unknown' for cloud step 'scan-step'"):
        await runner._execute_remote_run_type("unknown", timeout_seconds=10)


@pytest.mark.asyncio
async def test_remote_handler_runner_adds_typed_outputs_only_for_task_steps():
    from ofx.runner.cloud_step import _RemoteHandlerRunner

    runner = object.__new__(CloudStepRunner)
    runner.model = Step(task="httpx", run_with={"target": "example.com"}, timeout=1)
    runner._parse_task_output = lambda stdout: [{"parsed": stdout}]
    runner._run_type = RunType.TASK
    stored: list[tuple[object, object]] = []

    async def _execute_remote_run_type(run_type, *, timeout_seconds):
        assert run_type == RunType.TASK
        assert timeout_seconds == 60
        return "task-stdout"

    async def _reg_set(key, value):
        stored.append((key, value))

    runner._execute_remote_run_type = _execute_remote_run_type
    runner.reg_set = _reg_set
    runner.get_result = AsyncMock(return_value="result")

    assert await _RemoteHandlerRunner(runner).run() == "result"
    assert stored == [(
        "outputs",
        {"stdout": "task-stdout", "typed_outputs": [{"parsed": "task-stdout"}]},
    )]


@pytest.mark.asyncio
async def test_remote_handler_runner_skips_typed_outputs_for_non_task_steps():
    from ofx.runner.cloud_step import _RemoteHandlerRunner

    runner = object.__new__(CloudStepRunner)
    runner.model = Step(run="echo hi", timeout=1)
    runner._run_type = RunType.COMMAND
    stored: list[tuple[object, object]] = []

    async def _execute_remote_run_type(run_type, *, timeout_seconds):
        assert run_type == RunType.COMMAND
        assert timeout_seconds == 60
        return "cmd-stdout"

    async def _reg_set(key, value):
        stored.append((key, value))

    runner._execute_remote_run_type = _execute_remote_run_type
    runner.reg_set = _reg_set
    runner.get_result = AsyncMock(return_value="result")

    assert await _RemoteHandlerRunner(runner).run() == "result"
    assert stored == [(
        "outputs",
        {"stdout": "cmd-stdout"},
    )]


def test_task_parser_returns_none_when_task_missing(monkeypatch):
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(task="missing-task", run_with={"target": "example.com"})

    class _Registry:
        @staticmethod
        def get(_name):
            return None

    monkeypatch.setattr("ofx.tasks.registry.TaskRegistry", _Registry)
    runner._log_debug = lambda _message: None
    assert runner._parse_task_output("stdout") == []


def test_parse_task_output_instantiates_registered_parser(monkeypatch):
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(task="httpx", run_with={"target": "example.com"})

    class _Task:
        def parse_output(self, *, stdout, stderr):
            return [_TypedResult(stdout), _TypedResult(stderr)]

    class _TypedResult:
        def __init__(self, value):
            self.value = value

        def to_dict(self):
            return {"value": self.value}

    class _Registry:
        @staticmethod
        def get(_name):
            return _Task

    monkeypatch.setattr("ofx.tasks.registry.TaskRegistry", _Registry)
    monkeypatch.setattr(
        "ofx.runner.services.credential_store.should_store_creds",
        lambda *_args, **_kwargs: False,
    )
    runner._log_debug = lambda _message: None
    runner._log_info = lambda _message: None
    runner.parent = None

    assert runner._parse_task_output("stdout") == [
        {"value": "stdout"},
        {"value": ""},
    ]


def test_parse_task_output_stores_credentials_and_serializes(monkeypatch):
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(task="httpx", run_with={"target": "example.com"})
    stored = {}

    class _Result:
        def __init__(self, value):
            self.value = value

        def to_dict(self):
            return {"value": self.value}

    class _Task:
        def parse_output(self, *, stdout, stderr):
            return [_Result(stdout)]

    class _Registry:
        @staticmethod
        def get(_name):
            return _Task

    monkeypatch.setattr("ofx.tasks.registry.TaskRegistry", _Registry)
    monkeypatch.setattr(
        "ofx.runner.services.credential_store.should_store_creds",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "ofx.runner.services.credential_store.store_and_log_typed_outputs",
        lambda results, **_kwargs: stored.setdefault("results", list(results)),
    )
    runner._log_debug = lambda _message: None
    runner._log_info = lambda _message: None
    runner.parent = None

    output = runner._parse_task_output("parsed-stdout")

    assert output == [{"value": "parsed-stdout"}]
    assert len(stored["results"]) == 1


def test_parse_task_output_applies_side_effects_before_serializing(monkeypatch):
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(task="httpx", run_with={"target": "example.com"})

    calls: list[tuple[str, object]] = []

    class _TypedResult:
        def __init__(self, count: int) -> None:
            self._count = count

        def to_dict(self) -> dict[str, int]:
            calls.append(("typed", self._count))
            return {"count": self._count}

    parsed_results = [_TypedResult(1)]
    class _Task:
        def parse_output(self, *, stdout, stderr):
            calls.append(("parsed", stdout))
            return parsed_results

    class _Registry:
        @staticmethod
        def get(_name):
            return _Task

    monkeypatch.setattr("ofx.tasks.registry.TaskRegistry", _Registry)
    monkeypatch.setattr(
        "ofx.runner.services.credential_store.should_store_creds",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "ofx.runner.services.credential_store.store_and_log_typed_outputs",
        lambda results, **_kwargs: calls.append(("creds", results)),
    )
    runner._log_debug = lambda _message: None
    runner._log_info = lambda _message: None
    runner.parent = None

    assert runner._parse_task_output("stdout") == [{"count": 1}]
    assert calls == [
        ("parsed", "stdout"),
        ("creds", parsed_results),
        ("typed", 1),
    ]


def test_parse_task_output_returns_empty_and_logs_on_error():
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(task="httpx", run_with={"target": "example.com"})
    messages: list[str] = []
    runner._log_debug = messages.append
    runner._log_info = lambda _message: None

    class _Task:
        def parse_output(self, *, stdout, stderr):
            raise RuntimeError("boom")

    class _Registry:
        @staticmethod
        def get(_name):
            return _Task

    with monkeypatch.context() as m:
        m.setattr("ofx.tasks.registry.TaskRegistry", _Registry)
        runner.parent = None

        assert runner._parse_task_output("stdout") == []
    assert messages == ["Failed to parse task output for 'httpx': boom"]


@pytest.mark.asyncio
async def test_pre_run_sets_remote_work_dir_and_resolves_non_workflow_fields():
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(run="echo hi")
    runner.ctx = RunContext()
    runner.parent = SimpleNamespace(
        _cloud_config=SimpleNamespace(connection_type="ssh"),
        _produce_log=lambda message: message,
    )
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


def test_remote_exec_command_helpers_cover_platform_joining():
    posix_runner = object.__new__(CloudStepRunner)
    posix_runner.parent = SimpleNamespace(_cloud_config=SimpleNamespace(connection_type="ssh"))
    posix_runner._build_env_prefix = lambda: "export FOO=bar &&"
    posix_runner._resolve_remote_work_dir = lambda: "/tmp/ofx"

    windows_runner = object.__new__(CloudStepRunner)
    windows_runner.parent = SimpleNamespace(_cloud_config=SimpleNamespace(connection_type="winrm"))
    windows_runner._build_env_prefix = lambda: "SET FOO=bar"
    windows_runner._resolve_remote_work_dir = lambda: "C:\\ofx"

    assert windows_runner._build_remote_exec_command("echo hi") == (
        'SET FOO=bar && cd /d "C:\\ofx" && echo hi'
    )
    assert posix_runner._build_remote_exec_command("echo hi") == (
        "export FOO=bar && cd /tmp/ofx && echo hi"
    )


def test_remote_env_var_helpers_merge_runner_parent_and_step_env():
    runner = object.__new__(CloudStepRunner)
    runner.ctx = RunContext(envs={
        "REMOTE_FLEET_INPUT_FILE": "/tmp/targets.txt",
        "LOCAL_ONLY": "skip",
    })
    runner.model = Step(run="echo hi", env={"STEP_ONLY": "1"})
    runner.parent = SimpleNamespace(model=SimpleNamespace(env={"JOB_ONLY": "2"}))

    env_prefix = runner._build_env_prefix()
    assert 'REMOTE_FLEET_INPUT_FILE="/tmp/targets.txt"' in env_prefix
    assert 'JOB_ONLY="2"' in env_prefix
    assert 'STEP_ONLY="1"' in env_prefix


def test_step_log_helpers_build_name_run_type_and_message():
    runner = object.__new__(CloudStepRunner)
    runner.model = Step(run="echo hi", step_index=2, name="recon-step")
    workflow_runner = SimpleNamespace(model=SimpleNamespace(name="wf-a"), parent=None)
    runner.parent = SimpleNamespace(
        model=SimpleNamespace(jid="job-a"),
        parent=workflow_runner,
        _cloud_config=SimpleNamespace(connection_type="ssh", host="10.0.0.1"),
        _produce_log=lambda message: message,
    )
    runner._run_type = None

    timeline_params = runner._build_timeline_params(SimpleNamespace(outputs={}))
    assert timeline_params["source_host"] == "10.0.0.1"
    assert timeline_params["tags"] == "cloud"
    assert runner._produce_log("hello") == (
        "workflow[wf-a]job[job-a]step[2][recon-step][command] › hello"
    )
    runner._run_type = RunType.TASK
    assert runner._produce_log("hello") == (
        "workflow[wf-a]job[job-a]step[2][recon-step][task] › hello"
    )


@pytest.mark.asyncio
async def test_execute_remote_run_type_uses_cloud_opsec_mode_for_python_steps(monkeypatch, tmp_path):
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

    async def _run_remote_python_payload(payload, timeout=None):
        captured["payload"] = payload
        captured["timeout"] = timeout
        return "ok"

    runner._run_remote_python_payload = _run_remote_python_payload

    result = await runner._execute_remote_run_type(RunType.SCRIPT, timeout_seconds=21)

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
async def test_execute_remote_run_type_resolves_source_before_upload(monkeypatch, tmp_path):
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

    result = await runner._execute_remote_run_type(RunType.SCRIPT_FILE, timeout_seconds=21)

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
async def test_discover_python_logs_and_caches_selected_candidate() -> None:
    from ofx.runner.cloud_job import CloudJobRunner

    runner = object.__new__(CloudStepRunner)
    runner._remote = SimpleNamespace(
        run=lambda command, _timeout=None: "Python 3.11.0"
        if command.startswith("command -v python3")
        else (_ for _ in ()).throw(RuntimeError("unexpected"))
    )
    runner.parent = object.__new__(CloudJobRunner)
    runner.parent._cached_python = None
    info_messages: list[str] = []
    debug_messages: list[str] = []
    runner._log_info = info_messages.append
    runner._log_debug = debug_messages.append

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("asyncio.to_thread", _fake_to_thread)

        result = await runner._discover_python()

    assert result == "python3"
    assert info_messages == ["Discovered Python: python3"]
    assert debug_messages == []
    assert runner.parent._cached_python == "python3"


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
