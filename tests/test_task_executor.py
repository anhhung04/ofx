"""Tests for task executor command-runner helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ofx.runner import RunContext
from ofx.runner.executors.task import TaskExecutor
from ofx.runner.task_step import extract_output_item_target
from ofx.tasks.output_types import Port, Url

@pytest.mark.asyncio
async def test_pre_run_auto_installs_with_isolated_env_context(monkeypatch):
    captured_envs = []
    logs: list[str] = []

    class _FakeCommandRunner:
        def __init__(self, command_model, ctx):
            self.command_model = command_model
            self.ctx = ctx

        async def run(self):
            self.ctx.envs["MUTATED_BY"] = self.command_model.cmd
            captured_envs.append(dict(self.ctx.envs))
            return SimpleNamespace(
                status=SimpleNamespace(value="completed"),
                outputs={"exit_code": 0},
                error=None,
            )

    monkeypatch.setattr(
        "ofx.runner.executors.task.CommandRunner",
        _FakeCommandRunner,
    )
    monkeypatch.setattr("shutil.which", lambda _tool: "/usr/bin/fake-tool")
    monkeypatch.setattr(
        "ofx.runner.executors.task.TaskRegistry.get",
        lambda _name: lambda: SimpleNamespace(
            check_installed=lambda: False,
            get_install_command=lambda: "install fake-tool",
            cmd="fake-tool",
        ),
    )

    runner = SimpleNamespace(
        model=SimpleNamespace(task_name="fake-tool"),
        ctx=RunContext(envs={"BASE": "1"}),
        _log_info=logs.append,
        _log_warning=logs.append,
        _apply_profile_task_options=lambda: None,
    )

    await TaskExecutor().pre_run(runner)

    assert runner.ctx.envs["BASE"] == "1"
    assert "MUTATED_BY" not in runner.ctx.envs
    assert len(captured_envs) == 1
    assert captured_envs[0]["BASE"] == "1"
    assert captured_envs[0]["MUTATED_BY"] == "install fake-tool"
    assert logs == [
        "Tool 'fake-tool' not found - auto-installing with: install fake-tool",
        "Tool 'fake-tool' installed successfully",
    ]

@pytest.mark.asyncio
async def test_pre_run_sets_registered_task_instance(monkeypatch):
    class _Task:
        def check_installed(self):
            return True

    monkeypatch.setattr("ofx.runner.executors.task.TaskRegistry.get", lambda _name: _Task)
    runner = SimpleNamespace(
        model=SimpleNamespace(task_name="httpx"),
        _apply_profile_task_options=lambda: None,
    )

    await TaskExecutor().pre_run(runner)

    assert isinstance(runner._task, _Task)

@pytest.mark.asyncio
async def test_pre_run_raises_for_missing_task(monkeypatch):
    monkeypatch.setattr("ofx.runner.executors.task.TaskRegistry.get", lambda _name: None)
    monkeypatch.setattr("ofx.runner.executors.task.TaskRegistry.list_tasks", lambda: ["httpx"])
    runner = SimpleNamespace(
        model=SimpleNamespace(task_name="missing"),
        _apply_profile_task_options=lambda: None,
    )

    with pytest.raises(RuntimeError, match="Task 'missing' is not registered"):
        await TaskExecutor().pre_run(runner)

@pytest.mark.asyncio
async def test_pre_run_skips_install_when_task_already_installed(monkeypatch):
    install_calls: list[tuple[str, str]] = []
    task = SimpleNamespace(check_installed=lambda: True)
    runner = SimpleNamespace(model=SimpleNamespace(task_name="scan"), _log_warning=lambda _msg: None)
    executor = TaskExecutor()
    monkeypatch.setattr("ofx.runner.executors.task.TaskRegistry.get", lambda _name: lambda: task)
    runner._apply_profile_task_options = lambda: None

    class _FakeCommandRunner:
        def __init__(self, command_model, _ctx):
            install_calls.append((task.cmd, command_model.cmd))

        async def run(self):
            return SimpleNamespace(status=SimpleNamespace(value="completed"), error=None)

    monkeypatch.setattr("ofx.runner.executors.task.CommandRunner", _FakeCommandRunner)

    await executor.pre_run(runner)

    assert install_calls == []

@pytest.mark.asyncio
async def test_pre_run_auto_installs_when_command_present(monkeypatch):
    install_calls: list[tuple[str, str]] = []
    task = SimpleNamespace(
        check_installed=lambda: False,
        get_install_command=lambda: "install tool",
        cmd="tool",
    )
    runner = SimpleNamespace(model=SimpleNamespace(task_name="scan"), _log_warning=lambda _msg: None)
    executor = TaskExecutor()
    monkeypatch.setattr("ofx.runner.executors.task.TaskRegistry.get", lambda _name: lambda: task)
    runner.ctx = RunContext(envs={})
    runner._log_info = lambda _msg: None
    runner._apply_profile_task_options = lambda: None

    class _FakeCommandRunner:
        def __init__(self, command_model, _ctx):
            install_calls.append((task.cmd, command_model.cmd))

        async def run(self):
            return SimpleNamespace(status=SimpleNamespace(value="completed"), error=None)

    monkeypatch.setattr("ofx.runner.executors.task.CommandRunner", _FakeCommandRunner)
    monkeypatch.setattr("shutil.which", lambda _tool: "/usr/bin/tool")

    await executor.pre_run(runner)

    assert install_calls == [("tool", "install tool")]

@pytest.mark.asyncio
async def test_pre_run_warns_when_install_command_missing(monkeypatch):
    warnings: list[str] = []
    task = SimpleNamespace(
        check_installed=lambda: False,
        get_install_command=lambda: None,
        cmd="tool",
    )
    runner = SimpleNamespace(model=SimpleNamespace(task_name="scan"), _log_warning=warnings.append)
    monkeypatch.setattr("ofx.runner.executors.task.TaskRegistry.get", lambda _name: lambda: task)
    runner._apply_profile_task_options = lambda: None

    await TaskExecutor().pre_run(runner)

    assert warnings == [
        "Task 'scan' requires 'tool' but it is not installed and no install command is defined."
    ]

@pytest.mark.asyncio
async def test_pre_run_warns_when_tool_still_missing_after_install(monkeypatch):
    logs: list[str] = []

    class _FakeCommandRunner:
        def __init__(self, command_model, ctx):
            self.command_model = command_model
            self.ctx = ctx

        async def run(self):
            return SimpleNamespace(
                status=SimpleNamespace(value="completed"),
                outputs={"exit_code": 0},
                error=None,
            )

    monkeypatch.setattr(
        "ofx.runner.executors.task.CommandRunner",
        _FakeCommandRunner,
    )
    monkeypatch.setattr("shutil.which", lambda _tool: None)
    monkeypatch.setattr(
        "ofx.runner.executors.task.TaskRegistry.get",
        lambda _name: lambda: SimpleNamespace(
            check_installed=lambda: False,
            get_install_command=lambda: "install fake-tool",
            cmd="fake-tool",
        ),
    )

    runner = SimpleNamespace(
        model=SimpleNamespace(task_name="fake-tool"),
        ctx=RunContext(envs={}),
        _log_info=logs.append,
        _log_warning=logs.append,
        _apply_profile_task_options=lambda: None,
    )

    await TaskExecutor().pre_run(runner)

    assert logs == [
        "Tool 'fake-tool' not found - auto-installing with: install fake-tool",
        "Install command succeeded but 'fake-tool' still not found on PATH",
    ]

@pytest.mark.asyncio
async def test_finalize_task_execution_tags_typed_outputs_from_target_file(tmp_path):
    target_file = tmp_path / "targets.txt"
    target_file.write_text("example.com\n")
    recorded: list[tuple[str, dict]] = []
    runner = SimpleNamespace(
        reg_update=lambda key, value: recorded.append((key, dict(value))),
        _parse_outputs=lambda _result: [
            Port(ip="10.0.0.1", port=80),
            Url(url="https://example.com/path"),
        ],
        model=SimpleNamespace(target=str(target_file), store_creds=False, task_name="httpx"),
        _task=SimpleNamespace(export_output=False),
        _output_file=None,
        _log_debug=lambda _msg: None,
    )

    async def _reg_update(key, value):
        recorded.append((key, dict(value)))

    runner.reg_update = _reg_update

    await TaskExecutor()._finalize_task_execution(
        runner,
        outputs={},
        command="httpx -u x",
        executor=SimpleNamespace(capture_outputs_file=AsyncMock()),
        result=SimpleNamespace(exit_code=0, stdout="ok", stderr="", outputs={}),
    )

    typed_dicts = recorded[0][1]["typed_outputs"]
    assert typed_dicts[0]["_target"] == "10.0.0.1"
    assert typed_dicts[1]["_target"] == "example.com"

def test_extract_output_item_target_handles_invalid_url_gracefully():
    assert extract_output_item_target({"url": object()}) == ""

@pytest.mark.asyncio
async def test_finalize_task_execution_tags_typed_outputs_from_literal_target():
    recorded: list[tuple[str, dict]] = []
    runner = SimpleNamespace(
        _parse_outputs=lambda _result: [Port(ip="10.0.0.1", port=80)],
        model=SimpleNamespace(target="example.com", store_creds=False, task_name="httpx"),
        _task=SimpleNamespace(export_output=False),
        _output_file=None,
        _log_debug=lambda _msg: None,
    )

    async def _reg_update(key, value):
        recorded.append((key, dict(value)))

    runner.reg_update = _reg_update

    await TaskExecutor()._finalize_task_execution(
        runner,
        outputs={},
        command="httpx -u x",
        executor=SimpleNamespace(capture_outputs_file=AsyncMock()),
        result=SimpleNamespace(exit_code=0, stdout="ok", stderr="", outputs={}),
    )

    typed_dicts = recorded[0][1]["typed_outputs"]
    assert typed_dicts[0]["_target"] == "example.com"

@pytest.mark.asyncio
async def test_finalize_task_execution_without_target_preserves_plain_dicts():
    item = Port(ip="10.0.0.1", port=80)
    recorded: list[tuple[str, dict]] = []
    runner = SimpleNamespace(
        _parse_outputs=lambda _result: [item],
        model=SimpleNamespace(target="", store_creds=False, task_name="httpx"),
        _task=SimpleNamespace(export_output=False),
        _output_file=None,
        _log_debug=lambda _msg: None,
    )

    async def _reg_update(key, value):
        recorded.append((key, dict(value)))

    runner.reg_update = _reg_update

    await TaskExecutor()._finalize_task_execution(
        runner,
        outputs={},
        command="httpx -u x",
        executor=SimpleNamespace(capture_outputs_file=AsyncMock()),
        result=SimpleNamespace(exit_code=0, stdout="ok", stderr="", outputs={}),
    )

    typed_dicts = recorded[0][1]["typed_outputs"]
    assert typed_dicts == [item.to_dict()]

@pytest.mark.asyncio
async def test_finalize_task_execution_uses_blank_result_when_executor_returns_none():
    calls: list[tuple[str, object]] = []
    runner = SimpleNamespace(
        _parse_outputs=lambda result: calls.append(("parse", result.stdout)) or [],
        model=SimpleNamespace(store_creds=False, target="example.com", task_name="httpx"),
        _task=SimpleNamespace(export_output=False),
        _output_file=None,
        _log_debug=lambda _msg: None,
    )
    outputs: dict[str, object] = {}

    async def _capture_outputs_file(*_args, **_kwargs):
        return None

    async def _reg_update(_key, value):
        calls.append(
            (
                "update",
                (value["exit_code"], value["stdout"], value["stderr"], value["typed_outputs"]),
            )
        )

    runner.reg_update = _reg_update

    await TaskExecutor()._finalize_task_execution(
        runner,
        outputs=outputs,
        command="httpx -u x",
        executor=SimpleNamespace(capture_outputs_file=_capture_outputs_file),
        result=None,
    )

    assert calls == [
        ("parse", ""),
        ("update", (None, "", "", [])),
    ]

@pytest.mark.asyncio
async def test_do_run_sets_outputs_command_and_prepares_executor(monkeypatch):
    recorded: list[tuple[str, dict]] = []

    async def _reg_set(key, value):
        recorded.append((key, dict(value)))

    runner = SimpleNamespace(
        reg_set=_reg_set,
        _log_info=lambda _msg: None,
        _log_debug=lambda _msg: None,
        _output_file=None,
        model=SimpleNamespace(target="example.com", opts={}, shell="/bin/sh", working_directory=Path.cwd(), timeout_minutes=5),
        ctx=RunContext(envs={"BASE": "1"}),
        _on_stdout_line=lambda _line: None,
    )
    task_executor = TaskExecutor()

    runner._task = SimpleNamespace(
        build_command=lambda _target, **_opts: ("httpx -u x", Path("/tmp/result.txt")),
        supports_streaming=False,
        success_codes={0},
    )

    executor = SimpleNamespace()

    def _prepare_outputs_file():
        recorded.append(("prepared", {}))

    async def _execute():
        return SimpleNamespace(exit_code=0, stdout="ok", stderr="", outputs={})

    async def _capture_outputs_file(*_args, **_kwargs):
        return None

    executor.prepare_outputs_file = _prepare_outputs_file
    executor.execute = _execute
    executor.capture_outputs_file = _capture_outputs_file

    monkeypatch.setattr(
        "ofx.runner.executors.task.CommandExecutor",
        lambda _command_model, _envs: executor,
    )
    monkeypatch.setattr(task_executor, "_finalize_task_execution", AsyncMock())

    await task_executor.do_run(runner)

    assert runner._output_file == Path("/tmp/result.txt")
    assert recorded == [("outputs", {}), ("prepared", {})]
    task_executor._finalize_task_execution.assert_awaited_once_with(
        runner,
        outputs={},
        command="httpx -u x",
        executor=executor,
        result=SimpleNamespace(exit_code=0, stdout="ok", stderr="", outputs={}),
    )

@pytest.mark.asyncio
async def test_do_run_uses_streaming_executor_and_stdout_callback(monkeypatch):
    calls: list[object] = []
    task_executor = TaskExecutor()
    runner = SimpleNamespace(
        _task=SimpleNamespace(
            supports_streaming=True,
            success_codes={0},
            build_command=lambda _target, **_opts: ("httpx -u x", None),
        ),
        model=SimpleNamespace(
            task_name="httpx",
            target="example.com",
            opts={},
            shell="/bin/sh",
            working_directory=Path.cwd(),
            timeout_minutes=5,
            store_creds=False,
        ),
        reg_set=AsyncMock(),
        ctx=RunContext(envs={}),
        _log_info=lambda _msg: None,
        _on_stdout_line=lambda line: calls.append(("line", line)),
    )
    executor = SimpleNamespace(prepare_outputs_file=lambda: None)

    async def _execute_streaming(*, on_line):
        on_line("streamed")
        return SimpleNamespace(exit_code=0, stdout="ok", stderr="", outputs={})

    async def _finalize(_runner, **_kwargs):
        calls.append("finalize")

    executor.execute_streaming = _execute_streaming
    monkeypatch.setattr("ofx.runner.executors.task.CommandExecutor", lambda *_args: executor)
    monkeypatch.setattr(task_executor, "_finalize_task_execution", _finalize)

    await task_executor.do_run(runner)

    assert calls == [("line", "streamed"), "finalize"]

@pytest.mark.asyncio
async def test_do_run_adapts_command_for_profile(monkeypatch):
    captured_commands: list[str] = []
    task_executor = TaskExecutor()
    runner = SimpleNamespace(
        _task=SimpleNamespace(
            supports_streaming=False,
            success_codes={0},
            opts={},
            build_command=lambda _target, **_opts: ("whois example.com", None),
        ),
        model=SimpleNamespace(
            task_name="whois",
            target="example.com",
            opts={},
            shell="/bin/sh",
            working_directory=Path.cwd(),
            timeout_minutes=5,
            store_creds=False,
        ),
        reg_set=AsyncMock(),
        ctx=RunContext(vars={"profile_model": object()}, envs={}),
        _log_info=lambda _msg: None,
        _on_stdout_line=lambda _line: None,
    )

    executor = SimpleNamespace(prepare_outputs_file=lambda: None)

    async def _execute():
        return SimpleNamespace(exit_code=0, stdout="ok", stderr="", outputs={})

    async def _finalize(_runner, **_kwargs):
        return None

    def _command_executor(command_model, _envs):
        captured_commands.append(command_model.cmd)
        executor.execute = _execute
        return executor

    monkeypatch.setattr("ofx.runner.executors.task.CommandExecutor", _command_executor)
    monkeypatch.setattr(
        "ofx.runner.executors.task.adapt_task_command_for_profile",
        lambda command, **_kwargs: f"env HTTP_PROXY=socks5://127.0.0.1:9050 {command}",
    )
    monkeypatch.setattr(task_executor, "_finalize_task_execution", _finalize)

    await task_executor.do_run(runner)

    assert captured_commands == ["env HTTP_PROXY=socks5://127.0.0.1:9050 whois example.com"]

@pytest.mark.asyncio
async def test_do_run_raises_for_failed_exit_code_and_still_finalizes(monkeypatch):
    calls: list[str] = []
    task_executor = TaskExecutor()
    runner = SimpleNamespace(
        _task=SimpleNamespace(
            supports_streaming=False,
            success_codes={0},
            build_command=lambda _target, **_opts: ("httpx -u x", None),
        ),
        model=SimpleNamespace(
            task_name="httpx",
            target="example.com",
            opts={},
            shell="/bin/sh",
            working_directory=Path.cwd(),
            timeout_minutes=5,
            store_creds=False,
        ),
        reg_set=AsyncMock(),
        ctx=RunContext(envs={}),
        _log_info=lambda _msg: None,
        _on_stdout_line=lambda _line: None,
    )
    executor = SimpleNamespace(prepare_outputs_file=lambda: None)

    async def _execute():
        return SimpleNamespace(exit_code=2, stdout="", stderr="boom", outputs={})

    async def _finalize(_runner, **_kwargs):
        calls.append("finalize")

    executor.execute = _execute
    monkeypatch.setattr("ofx.runner.executors.task.CommandExecutor", lambda *_args: executor)
    monkeypatch.setattr(task_executor, "_finalize_task_execution", _finalize)

    with pytest.raises(RuntimeError, match="Command failed: boom"):
        await task_executor.do_run(runner)

    assert calls == ["finalize"]

@pytest.mark.asyncio
async def test_finalize_task_execution_merges_and_persists_outputs():
    recorded: list[tuple[str, dict]] = []

    async def _reg_update(key, value):
        recorded.append((key, dict(value)))

    async def _capture_outputs_file(*_args, **_kwargs):
        return None

    runner = SimpleNamespace(
        reg_update=_reg_update,
        _parse_outputs=lambda _result: [Port(ip="10.0.0.1", port=80)],
        model=SimpleNamespace(target="example.com", store_creds=False, task_name="httpx"),
        _task=SimpleNamespace(export_output=False),
        _output_file=None,
        _log_debug=lambda _msg: None,
    )
    execution = SimpleNamespace(
        capture_outputs_file=_capture_outputs_file,
    )
    result = SimpleNamespace(exit_code=0, stdout="ok", stderr="", outputs={"extra": 1})
    outputs: dict[str, object] = {}

    await TaskExecutor()._finalize_task_execution(
        runner,
        outputs=outputs,
        command="httpx -u x",
        executor=execution,
        result=result,
    )

    assert outputs["command"] == "httpx -u x"
    assert outputs["extra"] == 1
    assert outputs["typed_outputs"][0]["_target"] == "example.com"
    assert recorded == [("outputs", dict(outputs))]

@pytest.mark.asyncio
async def test_finalize_task_execution_runs_finalization_steps_in_order(monkeypatch):
    calls: list[object] = []
    typed_item = Port(ip="10.0.0.1", port=80)
    runner = SimpleNamespace(
        _parse_outputs=lambda result: calls.append(("parse", result.stdout)) or [typed_item],
        model=SimpleNamespace(store_creds=True, target="example.com", task_name="httpx"),
        _task=SimpleNamespace(export_output=False),
        _output_file=None,
        _log_debug=lambda _msg: None,
        _log_info=lambda _msg: None,
    )
    executor = SimpleNamespace()
    task_executor = TaskExecutor()
    outputs = {"seed": 1}

    async def _capture_outputs_file(_runner, _executor):
        calls.append(("capture", _executor is executor))

    async def _reg_update(_key, value):
        calls.append(("update", value["command"], list(value["typed_outputs"])))

    runner.reg_update = _reg_update

    async def _executor_capture_outputs_file(runner, key, log_fn):
        await _capture_outputs_file(runner, executor)

    executor.capture_outputs_file = _executor_capture_outputs_file
    monkeypatch.setattr(
        "ofx.runner.services.credential_store.store_and_log_typed_outputs",
        lambda typed_outputs, **_kwargs: calls.append(("store", list(typed_outputs))),
    )

    await task_executor._finalize_task_execution(
        runner,
        outputs=outputs,
        command="httpx -u x",
        executor=executor,
        result=SimpleNamespace(exit_code=0, stdout="ok", stderr="", outputs={}),
    )

    assert calls == [
        ("parse", "ok"),
        (
            "update",
            "httpx -u x",
            [{**typed_item.to_dict(), "_target": "example.com"}],
        ),
        ("capture", True),
        ("store", [typed_item]),
    ]

@pytest.mark.asyncio
async def test_finalize_task_execution_updates_registry_for_local_output_file(tmp_path):
    output_file = tmp_path / "result.txt"
    output_file.write_text("data")
    recorded: list[tuple[str, dict]] = []
    runner = SimpleNamespace(
        _parse_outputs=lambda _result: [],
        model=SimpleNamespace(store_creds=False, target="example.com", task_name="httpx"),
        _task=SimpleNamespace(export_output=False),
        _output_file=output_file,
        _log_debug=lambda _msg: None,
    )

    async def _reg_update(key, value):
        recorded.append((key, dict(value)))

    runner.reg_update = _reg_update
    outputs = {"stdout": "ok"}

    async def _capture_outputs_file(*_args, **_kwargs):
        return None

    await TaskExecutor()._finalize_task_execution(
        runner,
        outputs=outputs,
        command="httpx -u x",
        executor=SimpleNamespace(capture_outputs_file=_capture_outputs_file),
        result=SimpleNamespace(exit_code=0, stdout="ok", stderr="", outputs={}),
    )

    assert recorded == [
        (
            "outputs",
            {
                "stdout": "ok",
                "exit_code": 0,
                "stderr": "",
                "command": "httpx -u x",
                "typed_outputs": [],
                "output_file": str(output_file),
            },
        )
    ]

@pytest.mark.asyncio
async def test_finalize_task_execution_exports_and_cleans_output_file(tmp_path, monkeypatch):
    output_file = tmp_path / ".ofx_task_result.txt"
    output_file.write_text("data")
    recorded: list[tuple[str, dict]] = []
    removed: list[Path] = []
    exported = tmp_path / "scans" / "httpx_example.com.txt"

    runner = SimpleNamespace(
        _parse_outputs=lambda _result: [],
        model=SimpleNamespace(store_creds=False, target="example.com", task_name="httpx"),
        _task=SimpleNamespace(export_output=True),
        _output_file=output_file,
        _export_output_file=lambda: exported,
        _log_debug=lambda _msg: None,
        _log_info=lambda _msg: None,
    )

    async def _reg_update(key, value):
        recorded.append((key, dict(value)))

    async def _capture_outputs_file(*_args, **_kwargs):
        return None

    runner.reg_update = _reg_update
    monkeypatch.setattr(
        "ofx.runner.executors.task.remove_file",
        lambda path: removed.append(path) or None,
    )

    await TaskExecutor()._finalize_task_execution(
        runner,
        outputs={"stdout": "ok"},
        command="httpx -u x",
        executor=SimpleNamespace(capture_outputs_file=_capture_outputs_file),
        result=SimpleNamespace(exit_code=0, stdout="ok", stderr="", outputs={}),
    )

    assert removed == [output_file]
    assert recorded == [
        (
            "outputs",
            {
                "stdout": "ok",
                "exit_code": 0,
                "stderr": "",
                "command": "httpx -u x",
                "typed_outputs": [],
                "output_file": str(exported),
            },
        )
    ]

@pytest.mark.asyncio
async def test_finalize_task_execution_skips_or_stores_credentials_based_on_state():
    stored: list[list[object]] = []
    typed_item = Port(ip="10.0.0.1", port=80)

    async def _capture_outputs_file(*_args, **_kwargs):
        return None

    runner = SimpleNamespace(
        _parse_outputs=lambda _result: [typed_item],
        model=SimpleNamespace(store_creds=False, target="example.com", task_name="httpx"),
        _task=SimpleNamespace(export_output=False),
        _output_file=None,
        reg_update=AsyncMock(),
        _log_debug=lambda _msg: None,
        _log_info=lambda _msg: None,
    )
    task_executor = TaskExecutor()
    outputs: dict[str, object] = {}

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "ofx.runner.services.credential_store.store_and_log_typed_outputs",
            lambda typed_outputs, **_kwargs: stored.append(list(typed_outputs)) or len(typed_outputs),
        )

        await task_executor._finalize_task_execution(
            runner,
            outputs=outputs,
            command="httpx -u x",
            executor=SimpleNamespace(capture_outputs_file=_capture_outputs_file),
            result=SimpleNamespace(exit_code=0, stdout="ok", stderr="", outputs={}),
        )

        assert stored == []

        runner.model.store_creds = True
        await task_executor._finalize_task_execution(
            runner,
            outputs=outputs,
            command="httpx -u x",
            executor=SimpleNamespace(capture_outputs_file=_capture_outputs_file),
            result=SimpleNamespace(exit_code=0, stdout="ok", stderr="", outputs={}),
        )

        assert stored == [[typed_item]]
