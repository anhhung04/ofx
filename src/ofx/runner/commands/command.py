"""Command and script runners for executing shell commands and Python scripts"""

import asyncio
import atexit
import builtins
import contextlib
import io
import json
import logging
import os
from concurrent.futures import ProcessPoolExecutor
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
from ofx.runner.logging import bubble_log
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.runner.run_defaults import (
    resolve_model_shell,
    resolve_model_working_directory,
)
from ofx.runner.runner import BaseRunner
from ofx.settings import settings

# Shared ProcessPoolExecutor — avoids creating a new executor per script call.
_shared_executor: ProcessPoolExecutor | None = None


def write_outputs_file(outputs_file: str | os.PathLike[str] | None, **kwargs: Any) -> None:
    """Append `key=value` output lines, JSON-encoding structured values."""
    if not outputs_file:
        return

    with open(outputs_file, "a") as handle:
        for key, value in kwargs.items():
            if isinstance(value, (dict, list)):
                handle.write(f"{key}={json.dumps(value)}\n")
            else:
                handle.write(f"{key}={value}\n")


def _get_shared_executor() -> ProcessPoolExecutor:
    """Return or create the shared ProcessPoolExecutor."""
    global _shared_executor
    if _shared_executor is None:
        _shared_executor = ProcessPoolExecutor(max_workers=4)
        atexit.register(_shutdown_shared_executor)
    return _shared_executor


def _shutdown_shared_executor() -> None:
    """Shutdown the shared executor at process exit."""
    global _shared_executor
    if _shared_executor is not None:
        _shared_executor.shutdown(wait=False)
        _shared_executor = None


def exec_script_in_process(
    script,
    working_directory,
    job_model,
    step_model,
    workflow_model,
    ctx_model,
    inputs,
    secrets,
    channels_dir,
    outputs_file=None,
):
    """Execute script in a separate process with channel communication"""
    store = ChannelStore(channels_dir)

    # Make RUNNER_OUTPUTS / OFX_OUTPUTS available inside scripts
    if outputs_file:
        os.environ[RUNNER_OUTPUTS_ENV] = outputs_file
        os.environ[OFX_OUTPUTS_ENV] = outputs_file

    def _add_outputs(**kwargs):
        """Write key=value pairs to the OFX_OUTPUTS file.

        Lists and dicts are serialized as JSON. All other values
        are converted to strings.
        """
        write_outputs_file(outputs_file, **kwargs)

    from ofx.runner.findings_export import export_typed_outputs
    from ofx.runner.templates.helpers import _asm_helpers

    asm_funcs = _asm_helpers()

    globals_dict = {
        "__builtins__": builtins.__dict__,
        "__name__": "__main__",
        "os": os,
        "__job__": job_model,
        "__step__": step_model,
        "__workflow__": workflow_model,
        "__inputs__": inputs,
        "__ctx__": ctx_model,
        "__secrets__": secrets,
        "add_outputs": _add_outputs,
        "publish": lambda channel, data: store.publish(channel, data),
        "subscribe": lambda channel: store.subscribe(channel),
        "wait_for": lambda channel, condition, timeout=60: store.wait_for(
            channel, condition, timeout=timeout
        ),
        "export_typed_outputs": export_typed_outputs,
        # ASM integration (shared with template helpers)
        **asm_funcs,
    }

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    exit_code = 0
    original_cwd = os.getcwd()

    try:
        os.chdir(working_directory)
        with (
            contextlib.redirect_stdout(stdout_capture),
            contextlib.redirect_stderr(stderr_capture),
        ):
            exec(script, globals_dict)
    except Exception as e:
        exit_code = 1
        stderr_capture.write(str(e))
    finally:
        os.chdir(original_cwd)

    stdout = stdout_capture.getvalue()
    stderr = stderr_capture.getvalue()

    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
    }


class _ExecutionDefaultsMixin:
    """Shared inherited shell/working-directory resolution for command-like runners."""

    model: Command | Script

    def _resolve_shell(self) -> str:
        """Resolve shell path from explicit model state or parent defaults."""
        return resolve_model_shell(self, self.model)

    def _resolve_working_directory(self) -> Path:
        return resolve_model_working_directory(self, self.model)

    def _apply_execution_defaults(self) -> None:
        self.model.shell = self._resolve_shell()
        self.model.working_directory = self._resolve_working_directory()

    async def _pre_run(self) -> None:
        self._apply_execution_defaults()

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


class CommandRunner(_ExecutionDefaultsMixin, BaseRunner[Command]):
    def __init__(
        self,
        command_model: Command,
        ctx: RunContext,
        parent: BaseRunner | None = None,
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
            executor.raise_for_status(result.exit_code, result.stderr)
        except TimeoutError:
            raise RuntimeError(
                f"Command timed out after {self.model.timeout_minutes} minutes"
            ) from None
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Command error: {str(e)}") from e
        finally:
            if result is None:
                result = CommandExecutionResult(
                    exit_code=None, stdout="", stderr="", outputs={}
                )
            outputs.update(
                {
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
            outputs.update(result.outputs)
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
        return bubble_log(self.parent, str(message))


class ScriptRunner(_ExecutionDefaultsMixin, BaseRunner[Script]):
    def _script_scope_models(self) -> tuple[Any | None, Any | None, Any | None]:
        """Return workflow step scope models exposed inside executed scripts."""
        step_runner = self.parent
        job_runner = step_runner.parent if step_runner else None
        workflow_runner = job_runner.parent if job_runner else None
        return (
            getattr(job_runner, "model", None),
            getattr(step_runner, "model", None),
            getattr(workflow_runner, "model", None),
        )

    async def _do_run(self) -> None:
        """Execute a Python script using exec"""
        try:
            result = await asyncio.wait_for(
                self._exec_script(), timeout=self.model.timeout_minutes * 60
            )
            outputs = {
                "exit_code": result["exit_code"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
            }

            outputs_file_path = self.ctx.envs.get("RUNNER_OUTPUTS")
            if outputs_file_path:
                outputs.update(
                    parse_outputs_file(Path(outputs_file_path), self._log_debug)
                )

            await self.reg_set(RunnerRegistryKeys.OUTPUTS, outputs)
            status = (
                RunnerStatus.COMPLETED
                if result["exit_code"] == 0
                else RunnerStatus.FAILED
            )
            error = result["stderr"] if status == RunnerStatus.FAILED else None
            self._result = RunResult(
                name=self.name,
                run_id=self.run_id,
                status=status,
                error=error,
                outputs=outputs,
            )
            if status != RunnerStatus.COMPLETED:
                raise RuntimeError(error or "Script execution failed")
        except TimeoutError as timeout_exc:
            raise RuntimeError(
                f"Script timed out after {self.model.timeout_minutes} minutes"
            ) from timeout_exc

    async def _exec_script(self):
        """Run the script execution in a separate process"""
        # Use shared channels directory for inter-job communication
        channels_dir = settings.channels_dir
        outputs_file = self.ctx.envs.get(RUNNER_OUTPUTS_ENV)
        job_model, step_model, workflow_model = self._script_scope_models()

        executor = _get_shared_executor()
        future = executor.submit(
            exec_script_in_process,
            self.model.script,
            str(self.model.working_directory),
            job_model,
            step_model,
            workflow_model,
            self.ctx,
            self.ctx.inputs,
            self.ctx.secrets,
            channels_dir,
            outputs_file,
        )
        result = await asyncio.get_running_loop().run_in_executor(None, future.result)
        return result

    async def _post_run(self) -> None:
        await self._post_run_execution_log(
            failure_label="Script",
            result_label="script",
        )
