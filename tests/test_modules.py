"""Tests for the OFX module execution system.

Covers the module registry (builtin resolution + UDF spec loading), the
ModuleRunner (shell/python builtins and user-defined functions), the Step
model's module/uses/pipe constraints, and an end-to-end module-chain
workflow run.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

from ofx.models.step import RunType, Step
from ofx.models.workflow import Workflow
from ofx.modules import ModuleInvocation, ModuleRegistry, ModuleRunner
from ofx.runner import RunContext, RunnerStatus
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.runner.workflow import WorkflowRunner


def _capturing_logger() -> tuple[logging.Logger, list[str]]:
    logger = logging.getLogger(f"test-modules-{_capturing_logger._ids}")
    _capturing_logger._ids += 1
    logger.setLevel(logging.DEBUG)
    messages: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: messages.append(record.getMessage())
    logger.addHandler(handler)
    return logger, messages


_capturing_logger._ids = 0


def _write_udf(directory: Path, body: str, name: str = "my_mod.py") -> Path:
    path = directory / name
    path.write_text(body)
    return path


class TestModuleRegistry:
    """Builtin module resolution."""

    def test_builtin_resolution_bare_name(self):
        registry = ModuleRegistry()
        spec = registry.resolve("shell")
        assert spec.kind == "builtin"
        assert spec.name == "shell"
        assert spec.callable is not None

        spec = registry.resolve("python")
        assert spec.kind == "builtin"
        assert spec.name == "python"

    def test_builtin_resolution_prefixed(self):
        registry = ModuleRegistry()
        assert registry.resolve("builtin.shell").name == "shell"
        assert registry.resolve("builtin.python").name == "python"

    def test_builtin_names_sorted(self):
        registry = ModuleRegistry()
        assert registry.builtin_names == ("python", "shell")

    def test_unknown_name_error_lists_builtins(self):
        registry = ModuleRegistry()
        with pytest.raises(ValueError, match="Unknown module: 'nope'"):
            registry.resolve("nope")
        with pytest.raises(ValueError, match="shell"):
            registry.resolve("nope")
        with pytest.raises(ValueError, match="python"):
            registry.resolve("nope")

    def test_empty_spec_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ModuleRegistry().resolve("   ")


class TestUdfSpecParsing:
    """UDF spec parsing: ``<path>.py[::<function>]``."""

    def test_udf_function_defaults_to_run(self, tmp_path):
        _write_udf(tmp_path, "def run(ctx):\n    return {'ok': 1}\n")
        spec = ModuleRegistry(workflow_dir=tmp_path).resolve("my_mod.py")
        assert spec.kind == "udf"
        assert spec.function == "run"
        assert spec.file == tmp_path / "my_mod.py"
        assert spec.callable is not None

    def test_udf_explicit_function(self, tmp_path):
        _write_udf(tmp_path, "def helper(ctx):\n    return {'ok': 1}\n")
        spec = ModuleRegistry(workflow_dir=tmp_path).resolve("my_mod.py::helper")
        assert spec.kind == "udf"
        assert spec.function == "helper"
        assert spec.callable is not None

    def test_udf_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Module file not found"):
            ModuleRegistry(workflow_dir=tmp_path).resolve("missing.py")

    def test_udf_function_missing(self, tmp_path):
        _write_udf(tmp_path, "def run(ctx):\n    return {}\n")
        with pytest.raises(AttributeError, match="not found in module file"):
            ModuleRegistry(workflow_dir=tmp_path).resolve("my_mod.py::nope")

    def test_udf_not_callable(self, tmp_path):
        _write_udf(tmp_path, "run = 42\n")
        with pytest.raises(TypeError, match="not callable"):
            ModuleRegistry(workflow_dir=tmp_path).resolve("my_mod.py")

    def test_udf_spec_must_end_in_py(self):
        with pytest.raises(ValueError, match="expected '<path>.py"):
            ModuleRegistry().resolve("module.txt::run")


class TestModuleRunnerShell:
    """ModuleRunner for the builtin shell module."""

    @pytest.mark.asyncio
    async def test_shell_builtin_captures_stdout(self):
        invocation = ModuleInvocation(name="shell", args={"cmd": "echo hello-module"})
        runner = ModuleRunner(invocation, RunContext())
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["stdout"].strip() == "hello-module"
        assert outputs["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_shell_builtin_nonzero_exit_fails(self):
        invocation = ModuleInvocation(name="shell", args={"cmd": "exit 7"})
        runner = ModuleRunner(invocation, RunContext())
        result = await runner.run()
        assert result.status == RunnerStatus.FAILED
        assert result.error is not None
        assert "exit code 7" in result.error

    @pytest.mark.asyncio
    async def test_shell_builtin_requires_cmd(self):
        invocation = ModuleInvocation(name="shell", args={})
        runner = ModuleRunner(invocation, RunContext())
        result = await runner.run()
        assert result.status == RunnerStatus.FAILED
        assert "requires 'cmd'" in result.error


class TestModuleRunnerPython:
    """ModuleRunner for the builtin python module."""

    @pytest.mark.asyncio
    async def test_python_builtin_add_outputs_lands_in_outputs(self, tmp_path):
        outputs_file = tmp_path / "runner_outputs.txt"
        ctx = RunContext(envs={"RUNNER_OUTPUTS": str(outputs_file)})
        invocation = ModuleInvocation(
            name="python",
            args={"script": "add_outputs(greeting='hi')\nprint('py-ok')\n"},
        )
        runner = ModuleRunner(invocation, ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["greeting"] == "hi"
        assert outputs["stdout"].strip() == "py-ok"

    @pytest.mark.asyncio
    async def test_python_builtin_requires_script(self):
        invocation = ModuleInvocation(name="python", args={})
        runner = ModuleRunner(invocation, RunContext())
        result = await runner.run()
        assert result.status == RunnerStatus.FAILED
        assert "requires 'script' or 'script_file'" in result.error


class TestModuleRunnerUdf:
    """ModuleRunner executing user-defined functions."""

    @pytest.mark.asyncio
    async def test_udf_return_dict_merged_into_outputs(self, tmp_path):
        _write_udf(tmp_path, "def run(ctx):\n    return {'plan': ['a', 'b']}\n")
        invocation = ModuleInvocation(name="my_mod.py", args={"target": "x"})
        runner = ModuleRunner(invocation, RunContext(workflow_dir=tmp_path))
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["plan"] == ["a", "b"]
        assert outputs["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_udf_add_outputs(self, tmp_path):
        _write_udf(
            tmp_path,
            "def run(ctx):\n"
            "    ctx.add_outputs(open_ports=['22', '443'])\n"
            "    ctx.add_outputs(planned=2)\n",
        )
        invocation = ModuleInvocation(name="my_mod.py", args={})
        runner = ModuleRunner(invocation, RunContext(workflow_dir=tmp_path))
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["open_ports"] == ["22", "443"]
        assert outputs["planned"] == 2

    @pytest.mark.asyncio
    async def test_udf_log_works(self, tmp_path):
        _write_udf(tmp_path, "def run(ctx):\n    ctx.log('udf says hello')\n")
        logger, messages = _capturing_logger()
        invocation = ModuleInvocation(name="my_mod.py", args={})
        runner = ModuleRunner(
            invocation, RunContext(workflow_dir=tmp_path), logger=logger
        )
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        assert any("udf says hello" in message for message in messages)

    @pytest.mark.asyncio
    async def test_udf_exception_fails_with_traceback(self, tmp_path):
        _write_udf(
            tmp_path,
            "def run(ctx):\n    raise RuntimeError('boom-udf')\n",
        )
        invocation = ModuleInvocation(name="my_mod.py", args={})
        runner = ModuleRunner(invocation, RunContext(workflow_dir=tmp_path))
        result = await runner.run()
        assert result.status == RunnerStatus.FAILED
        assert result.error is not None
        assert "boom-udf" in result.error
        assert "Traceback" in result.error


class TestStepModuleModel:
    """Step model module/uses/pipe constraints and RunType dispatch."""

    def test_module_step_dispatch(self):
        step = Step(module="shell", run_with={"cmd": "echo hi"})
        assert step.get_run_type() == RunType.MODULE

    def test_module_uses_pipe_exclusivity(self):
        with pytest.raises(ValueError, match="exactly one"):
            Step(module="shell", uses="./other.yml")
        with pytest.raises(ValueError, match="exactly one"):
            Step(module="shell", pipe={"input": "{{ x }}"})

    def test_module_required(self):
        with pytest.raises(ValueError, match="exactly one"):
            Step(name="empty")

    def test_with_alias_carries_module_args(self):
        step = Step.model_validate(
            {"module": "shell", "with": {"cmd": "echo hi"}}
        )
        assert step.run_with == {"cmd": "echo hi"}


@pytest.mark.asyncio
async def test_module_chain_workflow_end_to_end(tmp_path):
    """Run a module-chain workflow (shell -> python -> UDF) via api.run_workflow."""
    _write_udf(
        tmp_path,
        "def run(ctx):\n"
        "    ports = ctx.inputs.get('ports', '')\n"
        "    ports = [p.strip() for p in str(ports).split(',') if p.strip()]\n"
        "    ctx.log('planning attacks')\n"
        "    ctx.add_outputs(planned=len(ports))\n"
        "    return {'plan': [{'port': p, 'service': 'ssh'} for p in ports]}\n",
    )
    workflow_yaml = """
name: module-chain-test
jobs:
  chain:
    steps:
      - name: recon
        module: shell
        with:
          cmd: echo "22,80,443"

      - name: parse
        module: python
        with:
          script: |
            raw = "{{ steps.recon.outputs.stdout }}".strip()
            add_outputs(open_ports=raw)

      - name: plan
        module: my_mod.py::run
        with:
          ports: "{{ steps.parse.outputs.open_ports }}"
"""
    wf_path = tmp_path / "wf.yml"
    wf_path.write_text(yaml.safe_dump(yaml.safe_load(workflow_yaml)))

    from ofx.runner.api import run_workflow

    result = await run_workflow(
        str(wf_path),
        secrets={},
        workflow_search_paths=[str(tmp_path)],
        output_path=tmp_path / "out",
    )
    assert result.status == RunnerStatus.COMPLETED

    # Same runner machinery: verify UDF outputs are visible in step outputs.
    workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
    workflow.workflow_path = wf_path
    runner = WorkflowRunner(workflow, RunContext(workflow_dir=tmp_path))
    run_result = await runner.run()
    assert run_result.status == RunnerStatus.COMPLETED

    chain = runner.runners["chain"]
    plan_runner = chain._runners["2"]
    plan_outputs = await plan_runner.reg_get(RunnerRegistryKeys.OUTPUTS)
    assert plan_outputs["planned"] == 3
    assert plan_outputs["plan"] == [
        {"port": "22", "service": "ssh"},
        {"port": "80", "service": "ssh"},
        {"port": "443", "service": "ssh"},
    ]
