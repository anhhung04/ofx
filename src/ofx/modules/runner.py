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
from ofx.modules.api import invoke_api_callable, is_ctx_style
from ofx.modules.base import (
    ModuleContext,
    ModuleResult,
    ModuleSpec,
)
from ofx.modules.registry import ModuleRegistry
from ofx.runner.channels import ChannelStore
from ofx.runner.context import RunContext
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.runner.run_defaults import resolve_model_run_default, resolve_model_shell
from ofx.runner.runner import Runner
from ofx.settings import DEFAULT_SHELL, settings

COMMAND_BUILTINS = ("shell", "python")
"""Builtin modules that run through the :class:`ModuleContext` path."""


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

    Every builtin — including ``shell`` and ``python`` — executes through
    :meth:`_invoke_udf` with a :class:`ModuleContext`; the legacy
    :class:`CommandRunner`/:class:`ScriptRunner` machinery is gone.
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
            module_result = await asyncio.to_thread(self._invoke_udf, spec)
            self._outputs.update(self._module_result_outputs(module_result))
            if module_result.exit_code not in (0, None):
                raise RuntimeError(self._udf_failure_message(module_result))
        finally:
            await self.reg_update(RunnerRegistryKeys.OUTPUTS, self._outputs)

    async def _post_run(self) -> None:
        if self._error:
            self._log_error(f"Module {self.model.name} failed: {self._error}")
        self._log_debug(
            f"Module result: \n---\n{await self.get_result()}\n---\n"
            f" with context: \n---\n{self.ctx}\n---"
        )

    def _scope_models(self) -> tuple[Any, Any, Any] | None:
        """Return ``(workflow_model, job_model, step_model)`` for python scripts.

        Walked from the step runner chain (ModuleRunner's parent is the
        StepRunner; its parent is the JobRunner; its parent is the
        WorkflowRunner), matching the standard resolution.
        """
        step_runner = self.parent
        step_model = getattr(step_runner, "model", None)
        job_runner = getattr(step_runner, "parent", None)
        job_model = getattr(job_runner, "model", None)
        workflow_model = getattr(getattr(job_runner, "parent", None), "model", None)
        if workflow_model is None and job_model is None and step_model is None:
            return None
        return (workflow_model, job_model, step_model)

    def _invoke_udf(self, spec: ModuleSpec) -> ModuleResult:
        """Execute a UDF, ``ofx.api`` module, or builtin synchronously.

        UDFs always receive the :class:`ModuleContext`. ``ofx.api`` functions
        are kwargs-style: the invocation args (merged workflow inputs plus the
        step's ``with:`` args) are filtered to their signature, so unrelated
        keys are ignored. A function that declares a ``ctx`` parameter is
        treated like a UDF and receives the context instead. Builtin modules
        (including ``shell``/``python``) are called with the context through
        their ``run(ctx)`` entry point.
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
        module_args = dict(self.model.args)
        if spec.kind == "builtin" and spec.name in COMMAND_BUILTINS:
            # The step-level timeout (ModuleInvocation.timeout_minutes) backs
            # the builtin's default; an explicit ``timeout_minutes`` in the
            # step's ``with:`` args still wins.
            module_args.setdefault("timeout_minutes", self.model.timeout_minutes)
        module_ctx = ModuleContext(
            inputs=dict(self.model.args),
            secrets=dict(self.ctx.secrets),
            env=dict(self.ctx.envs),
            args=module_args,
            working_directory=self.model.working_directory,
            workflow_dir=self.ctx.workflow_dir,
            logger=self._log_debug,
            add_outputs=lambda **kwargs: module_outputs.update(kwargs),
            publish=store.publish,
            subscribe=store.subscribe,
            wait_for=store.wait_for,
            scope_models=self._scope_models(),
            channels_dir=Path(settings.channels_dir),
            interactive=self.model.interactive,
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
            # Builtins return a ModuleResult carrying their own captured
            # stdout/stderr and exit code (e.g. the shell module's subprocess
            # output); surface those instead of the (empty) redirect capture.
            if returned.exit_code is not None:
                exit_code = returned.exit_code
            if returned.stdout:
                stdout_capture.write(returned.stdout)
            if returned.stderr:
                stderr_capture.write(returned.stderr)
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


__all__ = ["COMMAND_BUILTINS", "ModuleInvocation", "ModuleRunner"]
