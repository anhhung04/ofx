"""Step runner for executing workflow steps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.cloud.script_runtime import is_python_step_run_type
from ofx.models.job import Job
from ofx.models.step import RunType, Step
from ofx.runner.context import RunContext
from ofx.runner.error_helpers import coerce_timeout_minutes as _timeout_int
from ofx.runner.executors.step import StepExecutor
from ofx.runner.logging import bubble_context_log
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.runner.run_defaults import model_field_is_explicitly_set
from ofx.runner.runner import Runner
from ofx.runner.step_fields import BASE_STEP_TEMPLATE_FIELDS, RUN_TYPE_TEMPLATE_FIELDS
from ofx.runner.step_mixin import StepRunnerMixin

class StepRunner(StepRunnerMixin, Runner[Step]):
    def __init__(
        self,
        step: Step,
        context: RunContext,
        parent: Runner[Job],
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
        self._apply_retry_profile_defaults()
        self._run_type = self.model.get_run_type()

        if (
            self._run_type == RunType.COMMAND
            or is_python_step_run_type(self._run_type)
        ):
            from ofx.runner.commands.command_executor import prepare_outputs_file_env

            self._outputs_file = prepare_outputs_file_env(
                self.ctx.envs,
                interactive=self.model.interactive,
                include_ofx_alias=True,
            )

        fields = [*BASE_STEP_TEMPLATE_FIELDS, *RUN_TYPE_TEMPLATE_FIELDS[self._run_type]]
        await self._resolve_template_fields(fields)
        await self._resolve_timeout_field()
        self._ensure_run_if_condition("Step skipped due to run_if condition")

        self.update_env(self.model.env)
        resolved_run_with = await self._resolve_template(self.model.run_with)
        if resolved_run_with:
            self.update_inputs(resolved_run_with)
        await self.reg_set(
            RunnerRegistryKeys.MODEL,
            self.model.model_dump(exclude={"env", "secrets", "run_with"}),
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

__all__ = ["StepRunner", "_timeout_int"]
