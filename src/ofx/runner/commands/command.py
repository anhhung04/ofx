"""Command and script runners for executing shell commands and Python scripts"""

import logging
from pathlib import Path
from typing import Any

from ofx.models.command import Command, Script
from ofx.runner.core import BaseRunner, RunContext, RunnerRegistryKeys
from ofx.runner.registry import RegistryAdapter
from ofx.runner.commands.command_executor import CommandExecutionResult, CommandExecutor
from ofx.settings import DEFAULT_SHELL, settings

logger = logging.getLogger(settings.app_branding)


class CommandRunner(BaseRunner[Command]):
    """Optimized command runner with caching."""

    _shell_cache: dict[str, str] = {}

    def __init__(
        self,
        command_model: Command,
        ctx: RunContext,
        parent: "BaseRunner | None" = None,
    ):
        super().__init__(command_model, ctx, parent)
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
    def __init__(
        self,
        script_model: Script,
        ctx: RunContext,
        parent: "BaseRunner | None" = None,
    ):
        super().__init__(script_model, ctx, parent)
        command_model = Command(
            cmd=script_model.cmd,
            shell=script_model.shell,
            working_directory=script_model.working_directory,
            timeout_minutes=script_model.timeout_minutes,
            interactive=script_model.interactive,
        )
        self._command_runner: CommandRunner = CommandRunner(
            command_model,
            ctx=self.ctx,
            parent=self.parent,
        )

    async def _do_run(self) -> None:
        """Execute a Python script"""
        result = await self._command_runner.run()
        self._result = result
        if result.status.value != "completed":
            raise RuntimeError(result.error or "Script execution failed")

    async def _pre_run(self) -> None:
        """Pre-run hook"""
        pass

    async def _post_run(self) -> None:
        if self._error:
            self._log_error(f"Script failed: {self._error}")
        if self.model.script_file and self.model.script_file.exists():
            self.model.script_file.unlink(missing_ok=True)

    def _produce_log(self, message: Any) -> str:
        msg = str(message)
        if self.parent:
            return self.parent._produce_log(msg)
        return msg
