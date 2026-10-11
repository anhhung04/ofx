"""Module runner: execute builtin modules and user-defined functions."""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import traceback
from pathlib import Path
from typing import Any

from pydantic import Field

from ofx.models.base import OFXBaseModel
from ofx.models.command import Command, Script
from ofx.modules.api import invoke_api_callable, is_ctx_style
from ofx.modules.base import (
    PYTHON_MODULE_REQUIRES_SCRIPT,
    ModuleContext,
    ModuleResult,
    ModuleSpec,
)
from ofx.modules.registry import ModuleRegistry
from ofx.runner.channels import ChannelStore
from ofx.runner.commands.command import CommandRunner, ScriptRunner
from ofx.runner.context import RunContext, RunnerStatus, context_copy
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.runner.run_defaults import resolve_model_run_default, resolve_model_shell
from ofx.runner.runner import Runner
from ofx.settings import DEFAULT_SHELL, settings


class ModuleInvocation(OFXBaseModel):
    """Model describing a single module invocation."""

    name: str = Field(..., description="Module name or UDF spec")
    args: dict[str, Any] = Field(default_factory=dict)
    timeout_minutes: int = Field(default=1440, description="Timeout in minutes")
    shell: str = Field(default=DEFAULT_SHELL, description="Shell to use")
    working_directory: Path = Field(
        default_factory=Path.cwd,
        description="Working directory",
    )
    interactive: bool = Field(
        default=False,
        description="Interactive mode (stdin/stdout passthrough)",
    )


class ModuleRunner(Runner[ModuleInvocation]):
    """Run builtin modules and user-defined functions.

    Builtin ``shell``/``python`` modules delegate to the existing
    :class:`CommandRunner`/:class:`ScriptRunner` machinery; UDFs execute in a
    worker thread against a :class:`ModuleContext`.
    """

    def __init__(
        self,
        invocation: ModuleInvocation,
        ctx: RunContext,
        parent: Runner[Any] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(invocation, ctx, parent, None, logger=logger)
        self._outputs: dict[str, Any] = {}

    async def _pre_run(self) -> None:
        self.model.shell = resolve_model_shell(self, self.model)
        self.model.working_directory = resolve_model_run_default(
            self,
            self.model,
            "working_directory",
            fallback=Path.cwd(),
        )

    async def _do_run(self) -> None:
        await self.reg_set(RunnerRegistryKeys.OUTPUTS, self._outputs)
        registry = ModuleRegistry(workflow_dir=self.ctx.workflow_dir)
        spec = registry.resolve(self.model.name)
        try:
            if spec.kind in ("udf", "api"):
                module_result = await asyncio.to_thread(self._invoke_udf, spec)
                self._outputs.update(self._module_result_outputs(module_result))
                if module_result.exit_code not in (0, None):
                    raise RuntimeError(self._udf_failure_message(module_result))
            else:
                await self._run_builtin(spec)
        finally:
            await self.reg_update(RunnerRegistryKeys.OUTPUTS, self._outputs)

    async def _post_run(self) -> None:
        if self._error:
            self._log_error(f"Module {self.model.name} failed: {self._error}")
        self._log_debug(
            f"Module result: \n---\n{await self.get_result()}\n---\n"
            f" with context: \n---\n{self.ctx}\n---"
        )

    async def _run_builtin(self, spec: ModuleSpec) -> None:
        if spec.name == "shell":
            child: Runner[Any] = CommandRunner(
                self._build_command(),
                context_copy(self.ctx),
                parent=self,
            )
        elif spec.name == "python":
            child = ScriptRunner(
                self._build_script(),
                context_copy(self.ctx),
                parent=self,
            )
        else:
            raise RuntimeError(f"Unsupported builtin module: {spec.name}")
        result = await child.run()
        self._outputs.update(result.outputs)
        if result.status != RunnerStatus.COMPLETED:
            raise RuntimeError(
                result.error or f"Module {self.model.name} failed with exit code "
                f"{result.outputs.get('exit_code')}"
            )

    def _build_command(self) -> Command:
        cmd = self.model.args.get("cmd")
        if not cmd:
            raise RuntimeError("shell module requires 'cmd' in args")
        return Command(
            cmd=str(cmd),
            shell=self.model.shell,
            working_directory=self.model.working_directory,
            timeout_minutes=self.model.timeout_minutes,
            interactive=self.model.interactive and self.ctx.allow_interactive,
        )

    def _build_script(self) -> Script:
        args = self.model.args
        script = args.get("script")
        if not script and args.get("script_file"):
            script_file = Path(args["script_file"])
            if not script_file.is_absolute() and self.ctx.workflow_dir:
                script_file = self.ctx.workflow_dir / script_file
            try:
                script = script_file.read_text(encoding="utf-8")
            except OSError as exc:
                raise RuntimeError(
                    f"Failed to read script file {script_file}: {exc}"
                ) from exc
        if not script:
            raise RuntimeError(PYTHON_MODULE_REQUIRES_SCRIPT)
        return Script(
            script=str(script),
            shell=self.model.shell,
            working_directory=self.model.working_directory,
            timeout_minutes=self.model.timeout_minutes,
            interactive=self.model.interactive and self.ctx.allow_interactive,
        )

    def _invoke_udf(self, spec: ModuleSpec) -> ModuleResult:
        """Execute a UDF or ``ofx.api`` module synchronously (worker thread).

        UDFs always receive the :class:`ModuleContext`. ``ofx.api`` functions
        are kwargs-style: the invocation args (merged workflow inputs plus the
        step's ``with:`` args) are filtered to their signature, so unrelated
        keys are ignored. A function that declares a ``ctx`` parameter is
        treated like a UDF and receives the context instead.
        """
        callable_obj = spec.callable
        if callable_obj is None:
            return ModuleResult(
                exit_code=1,
                stderr=f"Module {spec.name} has no callable",
            )
        module_outputs: dict[str, Any] = {}
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        store = ChannelStore(settings.channels_dir)
        module_ctx = ModuleContext(
            inputs=dict(self.model.args),
            secrets=dict(self.ctx.secrets),
            env=dict(self.ctx.envs),
            args=dict(self.model.args),
            working_directory=self.model.working_directory,
            logger=self._log_debug,
            add_outputs=lambda **kwargs: module_outputs.update(kwargs),
            publish=store.publish,
            subscribe=store.subscribe,
            wait_for=store.wait_for,
        )

        def _call() -> Any:
            if spec.kind != "api":
                return callable_obj(module_ctx)
            if is_ctx_style(callable_obj):
                return callable_obj(module_ctx)
            return invoke_api_callable(callable_obj, dict(self.model.args))

        returned: Any = None
        try:
            with (
                contextlib.chdir(self.model.working_directory),
                contextlib.redirect_stdout(stdout_capture),
                contextlib.redirect_stderr(stderr_capture),
            ):
                returned = _call()
            exit_code = 0
        except Exception:
            stderr_capture.write(traceback.format_exc())
            exit_code = 1
        if isinstance(returned, ModuleResult):
            module_outputs.update(returned.outputs)
            returned_result = returned.result
        elif isinstance(returned, dict):
            module_outputs.update(returned)
            returned_result = None
        else:
            returned_result = returned
        return ModuleResult(
            exit_code=exit_code,
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue(),
            result=returned_result,
            outputs=module_outputs,
        )

    def _module_result_outputs(self, module_result: ModuleResult) -> dict[str, Any]:
        outputs: dict[str, Any] = {
            "exit_code": module_result.exit_code,
            "stdout": module_result.stdout,
            "stderr": module_result.stderr,
        }
        if module_result.result is not None:
            outputs["result"] = module_result.result
        outputs.update(module_result.outputs)
        return outputs

    def _udf_failure_message(self, module_result: ModuleResult) -> str:
        stderr = module_result.stderr.strip()
        tail = f": {stderr}" if stderr else ""
        return (
            f"Module {self.model.name} failed with exit code "
            f"{module_result.exit_code}{tail}"
        )


__all__ = ["ModuleInvocation", "ModuleRunner"]
