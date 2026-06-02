"""Command and script runners for executing shell commands and Python scripts"""

import asyncio
import atexit
import builtins
import contextlib
import io
import json
import logging
import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ofx.models.command import Command, Script
from ofx.runner.channels import ChannelStore
from ofx.runner.commands.command_executor import (
    OFX_OUTPUTS_ENV,
    RUNNER_OUTPUTS_ENV,
    CommandExecutionResult,
    CommandExecutor,
    parse_outputs_file,
)
from ofx.runner.context import RunContext, RunnerStatus, RunResult
from ofx.runner.logging import bubble_context_log
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.runner.run_defaults import (
    resolve_model_shell,
    resolve_model_run_default,
)
from ofx.runner.runner import Runner
from ofx.settings import settings

# Shared ProcessPoolExecutor — avoids creating a new executor per script call.
_shared_executor: ProcessPoolExecutor | None = None


@dataclass(frozen=True)
class _ScriptScopeModels:
    job_model: Any | None
    step_model: Any | None
    workflow_model: Any | None


@dataclass(frozen=True)
class _ScriptProcessInvocation:
    script: str
    working_directory: str
    scope_models: _ScriptScopeModels
    ctx: RunContext
    inputs: dict[str, Any]
    secrets: dict[str, Any]
    channels_dir: str
    outputs_file: str | None


@dataclass(frozen=True)
class _ScriptExecutionResult:
    exit_code: int
    stdout: str
    stderr: str


def write_outputs_file(outputs_file: str | os.PathLike[str] | None, **kwargs: Any) -> None:
    """Append `key=value` output lines, JSON-encoding structured values."""
    if not outputs_file:
        return

    with open(outputs_file, "a") as handle:
        for key, value in kwargs.items():
            serialized = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            handle.write(f"{key}={serialized}\n")


def exec_script_in_process(invocation: _ScriptProcessInvocation) -> _ScriptExecutionResult:
    """Execute script in a separate process with channel communication"""
    if invocation.outputs_file:
        path_str = str(invocation.outputs_file)
        os.environ.update({
            RUNNER_OUTPUTS_ENV: path_str,
            OFX_OUTPUTS_ENV: path_str,
        })
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    from ofx.runner.findings_export import export_typed_outputs

    store = ChannelStore(invocation.channels_dir)
    globals_dict = {
        "__builtins__": builtins.__dict__,
        "__name__": "__main__",
        "os": os,
        "__job__": invocation.scope_models.job_model,
        "__step__": invocation.scope_models.step_model,
        "__workflow__": invocation.scope_models.workflow_model,
        "__inputs__": invocation.inputs,
        "__ctx__": invocation.ctx,
        "__secrets__": invocation.secrets,
        "add_outputs": lambda **kwargs: write_outputs_file(invocation.outputs_file, **kwargs),
        "publish": lambda channel, data: store.publish(channel, data),
        "subscribe": lambda channel: store.subscribe(channel),
        "wait_for": lambda channel, condition, timeout=60: store.wait_for(
            channel, condition, timeout=timeout
        ),
        "export_typed_outputs": export_typed_outputs,
    }
    try:
        with (
            contextlib.chdir(invocation.working_directory),
            contextlib.redirect_stdout(stdout_capture),
            contextlib.redirect_stderr(stderr_capture),
        ):
            exec(invocation.script, globals_dict)
            exit_code = 0
    except Exception as exc:
        stderr_capture.write(str(exc))
        exit_code = 1

    return _ScriptExecutionResult(
        exit_code=exit_code,
        stdout=stdout_capture.getvalue(),
        stderr=stderr_capture.getvalue(),
    )


class _ExecutionDefaultsMixin:
    """Shared inherited shell/working-directory resolution for command-like runners."""

    model: Command | Script

    async def _pre_run(self) -> None:
        self.model.shell = resolve_model_shell(self, self.model)
        self.model.working_directory = resolve_model_run_default(
            self,
            self.model,
            "working_directory",
            fallback=Path.cwd(),
        )

    async def _post_run_execution_log(
        self,
        *,
        failure_label: str,
        result_label: str,
    ) -> None:
        if self._error:
            self._log_error(f"{failure_label} failed: {self._error}")
        self._log_debug(
            f"{result_label} result: \n---\n{await self.get_result()}\n---\n with context: \n---\n{self.ctx}\n---"
        )


class CommandRunner(_ExecutionDefaultsMixin, Runner[Command]):
    def __init__(
        self,
        command_model: Command,
        ctx: RunContext,
        parent: Runner | None = None,
        logger: logging.Logger | None = None,
    ):
        """Run shell commands with inherited execution defaults."""
        super().__init__(command_model, ctx, parent, None, logger=logger)
        self._outputs_file: Path | None = None

    async def _do_run(self) -> None:
        """Execute a shell command and capture output"""
        outputs: dict[str, Any] = {}
        await self.reg_set(RunnerRegistryKeys.OUTPUTS, outputs)
        if not self.model.shell or not Path(self.model.shell).exists():
            raise RuntimeError(f"Shell not found: {self.model.shell}") from None

        executor = CommandExecutor(self.model, self.ctx.envs)
        executor.prepare_outputs_file()
        self._outputs_file = executor.outputs_file
        result = None

        try:
            result = await executor.execute()
            if result.exit_code not in (0, None):
                error_message = f"Command failed with exit code {result.exit_code}"
                if result.stderr:
                    error_message = f"{error_message}: {result.stderr}"
                raise RuntimeError(error_message)
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Command error: {str(e)}") from e
        finally:
            final_result = result or CommandExecutionResult(
                exit_code=None,
                stdout="",
                stderr="",
                outputs={},
            )
            outputs.update(
                {
                    "exit_code": final_result.exit_code,
                    "stdout": final_result.stdout,
                    "stderr": final_result.stderr,
                }
            )
            outputs.update(final_result.outputs)
            await self.reg_update(RunnerRegistryKeys.OUTPUTS, outputs)
            await executor.capture_outputs_file(
                self,
                RunnerRegistryKeys.OUTPUTS,
                lambda msg: self._log_debug(msg),
            )

    async def _post_run(self) -> None:
        await self._post_run_execution_log(
            failure_label="Command",
            result_label="cmd",
        )

    def _produce_log(self, message: Any) -> str:
        return bubble_context_log(self.parent, message)


class ScriptRunner(_ExecutionDefaultsMixin, Runner[Script]):
    async def _do_run(self) -> None:
        """Execute a Python script using exec"""
        try:
            result = await asyncio.wait_for(
                self._exec_script(),
                timeout=self.model.timeout_minutes * 60,
            )
            outputs = {
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            outputs_file_path = self.ctx.envs.get("RUNNER_OUTPUTS")
            if outputs_file_path:
                outputs.update(
                    parse_outputs_file(Path(outputs_file_path), self._log_debug)
                )
            await self.reg_set(RunnerRegistryKeys.OUTPUTS, outputs)
            status = RunnerStatus.COMPLETED if result.exit_code == 0 else RunnerStatus.FAILED
            error = result.stderr if status == RunnerStatus.FAILED else None
            self._result = RunResult(
                name=self.name,
                run_id=self.run_id,
                status=status,
                error=error,
                outputs=outputs,
            )
            if status != RunnerStatus.COMPLETED:
                raise RuntimeError(result.stderr or "Script execution failed")
        except TimeoutError as timeout_exc:
            raise RuntimeError(
                f"Script timed out after {self.model.timeout_minutes} minutes"
            ) from timeout_exc

    async def _exec_script(self) -> _ScriptExecutionResult:
        """Run the script execution in a separate process"""
        step_runner = self.parent
        job_runner = getattr(step_runner, "parent", None)
        global _shared_executor
        if _shared_executor is None:
            if os.name == "nt":
                executor_kwargs: dict[str, Any] = {}
            else:
                try:
                    executor_kwargs = {"mp_context": mp.get_context("fork")}
                except ValueError:
                    executor_kwargs = {}
            _shared_executor = ProcessPoolExecutor(
                max_workers=4,
                **executor_kwargs,
            )
            atexit.register(_shared_executor.shutdown, wait=False)

        future = _shared_executor.submit(
            exec_script_in_process,
            _ScriptProcessInvocation(
                script=self.model.script,
                working_directory=str(self.model.working_directory),
                scope_models=_ScriptScopeModels(
                    job_model=getattr(job_runner, "model", None),
                    step_model=getattr(step_runner, "model", None),
                    workflow_model=getattr(getattr(job_runner, "parent", None), "model", None),
                ),
                ctx=self.ctx,
                inputs=self.ctx.inputs,
                secrets=self.ctx.secrets,
                channels_dir=settings.channels_dir,
                outputs_file=self.ctx.envs.get(RUNNER_OUTPUTS_ENV),
            ),
        )
        return await asyncio.get_running_loop().run_in_executor(None, future.result)

    async def _post_run(self) -> None:
        await self._post_run_execution_log(
            failure_label="Script",
            result_label="script",
        )
