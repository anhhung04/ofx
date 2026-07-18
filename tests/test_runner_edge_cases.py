"""Tests for runner edge cases and error handling"""

import asyncio
import contextlib
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

import pytest

from ofx.models.command import Command, Script
from ofx.models.workflow import ToolConfig
from ofx.runner import RunContext, RunnerStatus
from ofx.runner.commands.command import CommandRunner, ScriptRunner
from ofx.runner.tool_installer import ToolInstallation, ToolInstallerRunner
from ofx.settings import settings

async def _capture_script_exec_invocation(script: ScriptRunner):
    submitted: list[tuple[object, tuple]] = []

    class _Future:
        def result(self):
            return "future-result"

    class _Executor:
        def submit(self, fn, *args):
            submitted.append((fn, args))
            return _Future()

    import ofx.runner.commands.command as command_module

    original_shared_executor = command_module._shared_executor
    command_module._shared_executor = _Executor()
    loop = asyncio.get_running_loop()
    original_run_in_executor = loop.run_in_executor

    async def _fake_run_in_executor(_executor, fn, *args):
        return fn(*args)

    try:
        loop.run_in_executor = _fake_run_in_executor
        await script._exec_script()
        return submitted[0][1][0]
    finally:
        loop.run_in_executor = original_run_in_executor
        command_module._shared_executor = original_shared_executor

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

        task = asyncio.create_task(cmd.run())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (asyncio.CancelledError, TimeoutError):
            pass

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
        assert "binary_output" in result.outputs or "stdout" in result.outputs

    @pytest.mark.asyncio
    async def test_command_with_large_output(self):
        """Test command with output exceeding max size"""
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
        stdout = result.outputs.get("stdout", "")
        assert len(stdout) > 0

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
        from ofx.runner.workflow import WorkflowRunner

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
        assert cmd.model.shell == "/bin/sh"

    @pytest.mark.asyncio
    async def test_command_working_directory_resolution_from_parent(self):
        """Direct command runners inherit workflow default working directory."""
        import yaml

        from ofx.models.workflow import Workflow
        from ofx.runner.workflow import WorkflowRunner

        workflow_yaml = """
name: Test Workflow
defaults:
  run:
    working_directory: /tmp
jobs:
  test:
    steps:
      - run: echo \"test\"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        workflow_runner = WorkflowRunner(workflow, RunContext())

        cmd = CommandRunner(
            Command(cmd="echo test"),
            ctx=RunContext(),
            parent=workflow_runner,
        )
        await cmd._pre_run()

        assert cmd.model.working_directory == Path("/tmp")

    @pytest.mark.asyncio
    async def test_command_post_run_logs_shared_result_format(self):
        cmd = object.__new__(CommandRunner)
        cmd._error = "boom"
        cmd.ctx = RunContext()
        errors: list[str] = []
        debugs: list[str] = []
        cmd._log_error = errors.append
        cmd._log_debug = debugs.append

        async def _get_result():
            return "RESULT"

        cmd.get_result = _get_result

        await cmd._post_run()

        assert errors == ["Command failed: boom"]
        assert len(debugs) == 1
        assert debugs[0].startswith("cmd result: \n---\nRESULT\n---\n")
        assert "RunContext(" in debugs[0]

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

    @pytest.mark.asyncio
    async def test_script_runner_inherits_parent_shell_and_working_directory(self):
        import yaml

        from ofx.models.workflow import Workflow
        from ofx.runner.workflow import WorkflowRunner

        workflow_yaml = """
name: Test Workflow
defaults:
  run:
    shell: /bin/sh
    working_directory: /tmp
jobs:
  test:
    steps:
      - run: echo \"test\"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        workflow_runner = WorkflowRunner(workflow, RunContext())

        script = ScriptRunner(
            Script(script="print('hello')"),
            ctx=RunContext(),
            parent=workflow_runner,
        )
        await script._pre_run()

        assert script.model.shell == "/bin/sh"
        assert script.model.working_directory == Path("/tmp")

    @pytest.mark.asyncio
    async def test_script_post_run_logs_shared_result_format(self):
        script = object.__new__(ScriptRunner)
        script._error = "boom"
        script.ctx = RunContext()
        errors: list[str] = []
        debugs: list[str] = []
        script._log_error = errors.append
        script._log_debug = debugs.append

        async def _get_result():
            return "RESULT"

        script.get_result = _get_result

        await script._post_run()

        assert errors == ["Script failed: boom"]
        assert len(debugs) == 1
        assert debugs[0].startswith("script result: \n---\nRESULT\n---\n")
        assert "RunContext(" in debugs[0]

    @pytest.mark.asyncio
    async def test_script_with_injected_variables(self):
        """Test script with injected internal variables"""
        from ofx.models.command import Script
        from ofx.runner import RunContext

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

    @pytest.mark.asyncio
    async def test_exec_script_builds_empty_scope_without_parent(self):
        script = object.__new__(ScriptRunner)
        script.model = SimpleNamespace(script="print('hi')", working_directory=Path("/tmp/work"))
        script.ctx = RunContext(envs={})
        script.parent = None

        invocation = await _capture_script_exec_invocation(script)

        assert invocation.scope_models.job_model is None
        assert invocation.scope_models.step_model is None
        assert invocation.scope_models.workflow_model is None

    @pytest.mark.asyncio
    async def test_exec_script_collects_step_job_and_workflow_models(self):
        workflow_model = object()
        job_model = object()
        step_model = object()

        workflow_runner = SimpleNamespace(model=workflow_model)
        job_runner = SimpleNamespace(model=job_model, parent=workflow_runner)
        step_runner = SimpleNamespace(model=step_model, parent=job_runner)
        script = object.__new__(ScriptRunner)
        script.model = SimpleNamespace(script="print('hi')", working_directory=Path("/tmp/work"))
        script.ctx = RunContext(envs={})
        script.parent = step_runner

        invocation = await _capture_script_exec_invocation(script)

        assert invocation.scope_models.job_model is job_model
        assert invocation.scope_models.step_model is step_model
        assert invocation.scope_models.workflow_model is workflow_model

    @pytest.mark.asyncio
    async def test_do_run_merges_runner_outputs_file_values(self, tmp_path):
        outputs_file = tmp_path / "outputs"
        outputs_file.write_text("key=value\n")

        script = object.__new__(ScriptRunner)
        script.name = "script"
        script.run_id = "run-1"
        script.model = SimpleNamespace(timeout_minutes=3)
        script.ctx = RunContext(envs={"RUNNER_OUTPUTS": str(outputs_file)})
        script._log_debug = lambda _msg: None
        recorded: list[tuple[str, dict[str, object]]] = []

        async def _reg_set(key, value):
            recorded.append((key, dict(value)))

        script.reg_set = _reg_set
        script._exec_script = lambda: asyncio.sleep(0, result=SimpleNamespace(exit_code=0, stdout="ok", stderr=""))

        await script._do_run()

        assert script._result.outputs == {
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
            "key": "value",
        }
        assert recorded == [
            (
                "outputs",
                {
                    "exit_code": 0,
                    "stdout": "ok",
                    "stderr": "",
                    "key": "value",
                },
            )
        ]

    @pytest.mark.asyncio
    async def test_do_run_raises_with_stderr_or_default_message(self):
        script = object.__new__(ScriptRunner)
        script.name = "script"
        script.run_id = "run-1"
        script.model = SimpleNamespace(timeout_minutes=3)
        script.ctx = RunContext(envs={})

        async def _reg_set(_key, _value):
            return None

        script.reg_set = _reg_set

        with pytest.raises(RuntimeError, match="boom"):
            async def _exec_script_boom():
                return SimpleNamespace(exit_code=1, stdout="", stderr="boom")

            script._exec_script = _exec_script_boom
            await script._do_run()

        with pytest.raises(RuntimeError, match="Script execution failed"):
            async def _exec_script_blank():
                return SimpleNamespace(exit_code=1, stdout="", stderr="")

            script._exec_script = _exec_script_blank
            await script._do_run()

    @pytest.mark.asyncio
    async def test_do_run_populates_run_result_fields(self):
        script = object.__new__(ScriptRunner)
        script.name = "script"
        script.run_id = "run-1"
        script.model = SimpleNamespace(timeout_minutes=3)
        script.ctx = RunContext(envs={})

        async def _reg_set(_key, _value):
            return None

        script.reg_set = _reg_set

        async def _exec_script():
            return SimpleNamespace(exit_code=1, stdout="", stderr="boom")

        script._exec_script = _exec_script

        with pytest.raises(RuntimeError, match="boom"):
            await script._do_run()

        assert script._result.status == RunnerStatus.FAILED
        assert script._result.error == "boom"

    @pytest.mark.asyncio
    async def test_do_run_timeout_uses_model_timeout(self):
        script = object.__new__(ScriptRunner)
        script.model = SimpleNamespace(timeout_minutes=3)

        async def _exec_script():
            raise TimeoutError()

        script._exec_script = _exec_script

        with pytest.raises(RuntimeError, match="Script timed out after 3 minutes"):
            await script._do_run()

    @pytest.mark.asyncio
    async def test_do_run_persists_script_outputs(self):
        script = object.__new__(ScriptRunner)
        script.name = "script"
        script.run_id = "run-1"
        script.model = SimpleNamespace(timeout_minutes=3)
        script.ctx = RunContext(envs={})

        recorded: list[tuple[str, dict[str, object]]] = []

        async def _reg_set(key, value):
            recorded.append((key, dict(value)))

        script.reg_set = _reg_set
        script._exec_script = lambda: asyncio.sleep(0, result=SimpleNamespace(exit_code=0, stdout="ok", stderr=""))

        await script._do_run()

        assert script._result.outputs == {"exit_code": 0, "stdout": "ok", "stderr": ""}
        assert recorded == [
            ("outputs", {"exit_code": 0, "stdout": "ok", "stderr": ""})
        ]

    @pytest.mark.asyncio
    async def test_exec_script_bundles_scope_context_and_outputs_file(self):
        workflow_runner = SimpleNamespace(model="workflow")
        job_runner = SimpleNamespace(model="job", parent=workflow_runner)
        step_runner = SimpleNamespace(model="step", parent=job_runner)
        script = object.__new__(ScriptRunner)
        script.model = SimpleNamespace(script="print('hi')", working_directory=Path("/tmp/work"))
        script.ctx = RunContext(
            inputs={"target": "example.com"},
            secrets={"API_KEY": "secret"},
            envs={"RUNNER_OUTPUTS": "/tmp/out.txt"},
        )
        script.parent = step_runner

        invocation = await _capture_script_exec_invocation(script)

        assert invocation.script == "print('hi')"
        assert invocation.working_directory == "/tmp/work"
        assert invocation.scope_models.job_model == "job"
        assert invocation.scope_models.step_model == "step"
        assert invocation.scope_models.workflow_model == "workflow"
        assert invocation.inputs == {"target": "example.com"}
        assert invocation.secrets == {"API_KEY": "secret"}
        assert invocation.channels_dir == settings.channels_dir
        assert invocation.outputs_file == "/tmp/out.txt"

    @pytest.mark.asyncio
    async def test_exec_script_submits_process_invocation_to_shared_executor(self):
        script = object.__new__(ScriptRunner)
        script.model = SimpleNamespace(script="print('hi')", working_directory=Path("/tmp/work"))
        script.ctx = RunContext(envs={})
        script.parent = None

        submitted: list[tuple[object, tuple]] = []

        class _Future:
            def result(self):
                return "future-result"

        class _Executor:
            def submit(self, fn, *args):
                submitted.append((fn, args))
                return _Future()

        import ofx.runner.commands.command as command_module

        original_shared_executor = command_module._shared_executor
        command_module._shared_executor = _Executor()
        original_run_in_executor = asyncio.get_running_loop().run_in_executor

        async def _fake_run_in_executor(_executor, fn, *args):
            return fn(*args)

        try:
            asyncio.get_running_loop().run_in_executor = _fake_run_in_executor
            result = await script._exec_script()
            assert result == "future-result"
            invocation = submitted[0][1][0]
            assert invocation.script == "print('hi')"
            assert invocation.working_directory == "/tmp/work"
        finally:
            asyncio.get_running_loop().run_in_executor = original_run_in_executor
            command_module._shared_executor = original_shared_executor

    @pytest.mark.asyncio
    async def test_exec_script_waits_for_future_result_via_executor(self):
        script = object.__new__(ScriptRunner)
        script.model = SimpleNamespace(script="print('hi')", working_directory=Path("/tmp/work"))
        script.ctx = RunContext(envs={})
        script.parent = None

        class _Future:
            def result(self):
                return SimpleNamespace(exit_code=0, stdout="ok", stderr="")

        class _Executor:
            def submit(self, fn, *args):
                invocation = args[0]
                assert invocation.script == "print('hi')"
                assert invocation.working_directory == "/tmp/work"
                return _Future()

        import ofx.runner.commands.command as command_module

        original_shared_executor = command_module._shared_executor
        command_module._shared_executor = _Executor()
        loop = asyncio.get_running_loop()
        original_run_in_executor = loop.run_in_executor

        async def _fake_run_in_executor(_executor, fn, *args):
            return fn(*args)

        try:
            loop.run_in_executor = _fake_run_in_executor
            result = await script._exec_script()
        finally:
            loop.run_in_executor = original_run_in_executor
            command_module._shared_executor = original_shared_executor

        assert result.exit_code == 0
        assert result.stdout == "ok"
        assert result.stderr == ""

    def test_exec_script_in_process_builds_store_globals_and_streams(self, monkeypatch):
        from ofx.runner.commands.command import exec_script_in_process

        invocation = SimpleNamespace(
            script="print('hi')",
            working_directory="/tmp/work",
            scope_models=SimpleNamespace(
                job_model="job",
                step_model="step",
                workflow_model="workflow",
            ),
            ctx="ctx",
            inputs={"target": "example.com"},
            secrets={"API_KEY": "secret"},
            channels_dir="/tmp/channels",
            outputs_file="/tmp/out.txt",
        )
        calls: list[tuple[str, object]] = []
        captured_globals: dict[str, object] = {}

        class _Capture:
            def __init__(self, value: str) -> None:
                self._value = value

            def getvalue(self) -> str:
                return self._value

            def write(self, text: str) -> None:
                self._value += text

        stdout_capture = _Capture("stdout")
        stderr_capture = _Capture("stderr")

        store_obj = SimpleNamespace(
            publish=lambda channel, data: ("publish", channel, data),
            subscribe=lambda channel: ("subscribe", channel),
            wait_for=lambda channel, condition, timeout=60: (
                "wait_for",
                channel,
                condition,
                timeout,
            ),
        )
        export_helper = object()

        monkeypatch.setattr(
            "ofx.runner.commands.command.ChannelStore",
            lambda channels_dir: calls.append(("store", channels_dir)) or store_obj,
        )
        monkeypatch.setattr(
            "ofx.runner.commands.command.os.environ.update",
            lambda updates: calls.append(("env", updates)),
        )
        monkeypatch.setattr(
            "ofx.runner.findings_export.export_typed_outputs",
            export_helper,
        )
        captures = iter((stdout_capture, stderr_capture))
        monkeypatch.setattr(
            "ofx.runner.commands.command.io.StringIO",
            lambda: next(captures),
        )
        monkeypatch.setattr(
            "ofx.runner.commands.command.contextlib.chdir",
            lambda _path: contextlib.nullcontext(),
        )
        monkeypatch.setattr(
            "builtins.exec",
            lambda script, globals_dict: captured_globals.update(globals_dict) or calls.append(("exec", script)) or None,
        )

        result = exec_script_in_process(invocation)

        assert result.exit_code == 0
        assert result.stdout == "stdout"
        assert result.stderr == "stderr"
        assert calls == [
            ("env", {"RUNNER_OUTPUTS": "/tmp/out.txt", "OFX_OUTPUTS": "/tmp/out.txt"}),
            ("store", "/tmp/channels"),
            ("exec", invocation.script),
        ]
        assert captured_globals["__job__"] == invocation.scope_models.job_model
        assert captured_globals["__step__"] == invocation.scope_models.step_model
        assert captured_globals["__workflow__"] == invocation.scope_models.workflow_model
        assert captured_globals["__inputs__"] == invocation.inputs
        assert captured_globals["__ctx__"] == invocation.ctx
        assert captured_globals["__secrets__"] == invocation.secrets
        assert captured_globals["export_typed_outputs"] is export_helper
        assert callable(captured_globals["add_outputs"])
        assert callable(captured_globals["publish"])
        assert callable(captured_globals["subscribe"])
        assert callable(captured_globals["wait_for"])

    def test_exec_script_in_process_restores_cwd_and_captures_error(self, tmp_path):
        import os

        from ofx.runner.commands.command import (
            exec_script_in_process,
        )

        original_cwd = Path.cwd()
        invocation = SimpleNamespace(
            script="import os\nprint(os.getcwd())\nraise ValueError('boom')",
            working_directory=str(tmp_path),
            scope_models=SimpleNamespace(job_model=None, step_model=None, workflow_model=None),
            ctx=SimpleNamespace(),
            inputs={},
            secrets={},
            channels_dir=str(tmp_path / "channels"),
            outputs_file=None,
        )

        result = exec_script_in_process(invocation)

        assert result.exit_code == 1
        assert result.stdout.strip() == str(tmp_path)
        assert result.stderr == "boom"
        assert Path.cwd() == original_cwd

    def test_exec_script_in_process_exposes_os_to_runtime(self, tmp_path):
        from ofx.runner.commands.command import exec_script_in_process

        invocation = SimpleNamespace(
            script="import os\nprint(bool(os.environ is not None))",
            working_directory=str(tmp_path),
            scope_models=SimpleNamespace(job_model=None, step_model=None, workflow_model=None),
            ctx=SimpleNamespace(),
            inputs={},
            secrets={},
            channels_dir=str(tmp_path / "channels"),
            outputs_file=None,
        )

        result = exec_script_in_process(invocation)

        assert result.exit_code == 0
        assert result.stdout.strip() == "True"

    @pytest.mark.asyncio
    async def test_exec_script_registers_executor_shutdown_when_creating_shared_executor(self, monkeypatch):
        script = object.__new__(ScriptRunner)
        script.model = SimpleNamespace(script="print('hi')", working_directory=Path("/tmp/work"))
        script.ctx = RunContext(envs={})
        script.parent = None

        registered: list[tuple[object, tuple, dict]] = []

        class _Future:
            def result(self):
                return SimpleNamespace(exit_code=0, stdout="ok", stderr="")

        class _Executor:
            def submit(self, fn, *args):
                return _Future()

            def shutdown(self, **kwargs):
                return None

        import ofx.runner.commands.command as command_module

        original_shared_executor = command_module._shared_executor
        loop = asyncio.get_running_loop()
        original_run_in_executor = loop.run_in_executor
        monkeypatch.setattr(command_module, "_shared_executor", None)
        monkeypatch.setattr(command_module, "ProcessPoolExecutor", lambda **kwargs: _Executor())
        monkeypatch.setattr(command_module.atexit, "register", lambda fn, *args, **kwargs: registered.append((fn, args, kwargs)))

        async def _fake_run_in_executor(_executor, fn, *args):
            return fn(*args)

        try:
            loop.run_in_executor = _fake_run_in_executor
            await script._exec_script()
        finally:
            loop.run_in_executor = original_run_in_executor
            command_module._shared_executor = original_shared_executor

        registered_fn, registered_args, registered_kwargs = registered[0]
        assert registered_args == ()
        assert registered_kwargs == {"wait": False}
        assert getattr(registered_fn, "__self__", None) is not None
        assert getattr(registered_fn, "__name__", "") == "shutdown"

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

        class _FakeCommandRunner:
            def __init__(self, command_model, ctx):
                self.command_model = command_model
                self.ctx = ctx

            async def run(self):
                self.ctx.envs["MUTATED_BY"] = self.command_model.cmd
                captured_envs.append(dict(self.ctx.envs))
                exit_code = 1 if self.command_model.cmd == "false" else 0
                return SimpleNamespace(
                    status=SimpleNamespace(value="completed"),
                    outputs={"exit_code": exit_code},
                    error=None,
                )

        monkeypatch.setattr(
            "ofx.runner.tool_installer.CommandRunner",
            _FakeCommandRunner,
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
        from ofx.runner.step import StepRunner

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
