"""Command and script runners for executing shell commands and Python scripts"""

import asyncio
import builtins
import contextlib
import io
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from ofx.models.command import Command, Script
from ofx.runner.channels import ChannelStore
from ofx.runner.commands.command_executor import CommandExecutionResult, CommandExecutor
from ofx.runner.core import (
    BaseRunner,
    RunContext,
    RunnerRegistryKeys,
    RunnerStatus,
    RunResult,
)
from ofx.settings import DEFAULT_SHELL, settings


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
):
    """Execute script in a separate process with channel communication"""
    store = ChannelStore(channels_dir)

    globals_dict = {
        "__builtins__": builtins.__dict__,
        "__name__": "__main__",
        "__job__": job_model,
        "__step__": step_model,
        "__workflow__": workflow_model,
        "__inputs__": inputs,
        "__ctx__": ctx_model,
        "__secrets__": secrets,
        "publish": lambda channel, data: store.publish(channel, data),
        "subscribe": lambda channel: store.subscribe(channel),
        "wait_for": lambda channel, condition, timeout=60: store.wait_for(
            channel, condition, timeout=timeout
        ),
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


class CommandRunner(BaseRunner[Command]):
    _shell_cache: dict[str, str] = {}

    def __init__(
        self,
        command_model: Command,
        ctx: RunContext,
        parent: BaseRunner | None = None,
        logger: logging.Logger | None = None,
    ):
        """Optimized command runner with caching."""
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

    async def _pre_run(self) -> None:
        self.model.shell = self._resolve_shell()

    async def _post_run(self) -> None:
        if self._error:
            self._log_error(f"Command failed: {self._error}")
        self._log_debug(
            f"cmd result: \n---\n{await self.get_result()}\n---\n with context: \n---\n{self.ctx}\n---"
        )

    def _produce_log(self, message: Any) -> str:
        msg = str(message)
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    def _resolve_shell(self) -> str:
        """Resolve shell path from hierarchy or use default /bin/bash"""
        if self.model.shell:
            return self.model.shell

        parent = getattr(self, "parent", None)
        if parent and getattr(parent, "parent", None):
            grandparent = parent.parent
            grandparent_model = getattr(grandparent, "model", None)
            if grandparent_model:
                defaults = getattr(grandparent_model, "defaults", None)
                if defaults and hasattr(defaults, "run"):
                    parent_shell = getattr(defaults.run, "shell", None)
                    if parent_shell:
                        return parent_shell

        return DEFAULT_SHELL


class ScriptRunner(BaseRunner[Script]):
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

        with ProcessPoolExecutor() as executor:
            future = executor.submit(
                exec_script_in_process,
                self.model.script,
                str(self.model.working_directory),
                self.parent.parent.model
                if self.parent and self.parent.parent
                else None,
                self.parent.model if self.parent else None,
                self.parent.parent.parent.model
                if self.parent and self.parent.parent and self.parent.parent.parent
                else None,
                self.ctx,
                self.ctx.inputs,
                self.ctx.secrets,
                channels_dir,
            )
            result = await asyncio.get_event_loop().run_in_executor(None, future.result)
            return result

    async def _pre_run(self) -> None:
        """Pre-run hook"""
        pass

    async def _post_run(self) -> None:
        if self._error:
            self._log_error(f"Script failed: {self._error}")
        self._log_debug(
            f"script result: \n---\n{await self.get_result()}\n---\n with context: \n---\n{self.ctx}\n---"
        )

    def _produce_log(self, message: Any) -> str:
        msg = str(message)
        if self.parent:
            return self.parent._produce_log(msg)
        return msg
