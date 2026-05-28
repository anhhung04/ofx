"""Step runner for executing workflow steps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.cloud.script_runtime import is_python_step_run_type
from ofx.models.job import Job
from ofx.models.step import RunType, Step
from ofx.runner.context import (
    RunContext,
    RunnerContextBuilder,
)
from ofx.runner.error_helpers import coerce_timeout_minutes as _timeout_int
from ofx.runner.executors.step import StepExecutor
from ofx.runner.handlers import registry as default_handler_registry
from ofx.runner.logging import bubble_context_log
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.runner.run_defaults import model_field_is_explicitly_set, resolve_model_shell
from ofx.runner.runner import BaseRunner
from ofx.runner.step_mixin import StepRunnerMixin


class StepRunner(StepRunnerMixin, BaseRunner[Step]):
    def __init__(
        self,
        step: Step,
        context: RunContext,
        parent: BaseRunner[Job],
        executor: StepExecutor | None = None,
    ):
        step_executor = executor or StepExecutor()
        super().__init__(
            step,
            context,
            parent,
            parent.registry,
            executor=step_executor,
        )
        self._outputs_file: Path | None = None

    async def _pre_run(self) -> None:
        self._prepare_step_run_type()

        if self._run_type == RunType.COMMAND or is_python_step_run_type(self._run_type):
            from ofx.runner.commands.command_executor import prepare_outputs_file_env

            self._outputs_file = prepare_outputs_file_env(
                self.ctx.envs,
                interactive=self.model.interactive,
                include_ofx_alias=True,
            )

        await self._resolve_step_pre_run_fields()

        if not self._evaluate_run_if(self.model.run_if, self._run_if_context()):
            self._cancel_step_for_unmet_condition("Step skipped due to run_if condition")

        self.ctx = RunnerContextBuilder(self.ctx).with_env(self.model.env)
        resolved_run_with = await self._resolve_template(self.model.run_with)
        if resolved_run_with:
            self.ctx = RunnerContextBuilder(self.ctx).with_inputs(resolved_run_with)
        await self.reg_set(
            RunnerRegistryKeys.MODEL,
            self.model.model_dump(exclude={"env", "secrets", "run_with"}),
        )

    def _create_runner(self) -> BaseRunner:
        if (
            self.model.interactive
            and self.ctx.allow_interactive
            and self._run_type == RunType.WORKFLOW
        ):
            self._log_warning(
                "Interactive mode is not supported for workflow steps ('uses'). "
                "Ignoring interactive flag."
            )
        registry = getattr(self, "_handler_registry", default_handler_registry)
        return registry.create_runner(self._run_type, self)

    def _save_output_file(self, stdout: str, outputs: dict) -> None:
        self._save_runner_output(
            stdout,
            outputs,
            missing_output_path_message="No output_path configured, skipping log file save.",
            warn_on_missing_output_path=True,
        )

    def _produce_log(self, message: Any) -> str:
        return bubble_context_log(
            self.parent,
            message,
            step_index=getattr(self.model, "step_index", "?"),
        )

    def _resolve_working_dir(self) -> Path:
        base_path = Path(self.ctx.vars.get("working_directory", Path.cwd()))
        if not base_path.is_absolute():
            base_path = base_path.resolve()

        if not model_field_is_explicitly_set(self.model, "working_directory"):
            return base_path

        step_path = Path(self.model.working_directory)
        if step_path.is_absolute():
            return step_path

        return (base_path / step_path).resolve()

    def _resolve_shell(self) -> str:
        return resolve_model_shell(self, self.model)

    def _resolve_store_creds(self) -> bool:
        from ofx.runner.services.credential_store import should_store_creds

        parent_model = self.parent.model if self.parent else None
        return should_store_creds(self.model.store_creds, parent_model)


__all__ = ["StepRunner", "_timeout_int"]
