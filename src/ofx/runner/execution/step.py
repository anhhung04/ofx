"Step runner for executing workflow steps"

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.models.job import Job
from ofx.models.step import RunType, Step
from ofx.runner.context import RunnerContextBuilder
from ofx.runner.core import (
    BaseRunner,
    ConditionNotMetError,
    RunContext,
    RunnerRegistryKeys,
    RunnerStatus,
)
from ofx.runner.core.models import RunResult
from ofx.runner.execution.step_mixin import StepRunnerMixin
from ofx.runner.executors.step import StepExecutor
from ofx.runner.logging import LogContext, get_logger


def _timeout_int(value: int | str) -> int:
    """Coerce a template-resolved timeout (may arrive as str) to int."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 60 * 24


logger = get_logger()


class StepRunner(StepRunnerMixin, BaseRunner[Step]):
    def __init__(
        self,
        step: Step,
        context: RunContext,
        parent: BaseRunner[Job],
        executor: StepExecutor | None = None,
    ):
        step_executor = executor or StepExecutor()
        self._step_executor: StepExecutor = step_executor
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

        if self._run_type in (RunType.COMMAND, RunType.SCRIPT, RunType.SCRIPT_FILE):
            from ofx.utils.tempfiles import make_temp_file

            self._outputs_file = make_temp_file(prefix=".tmp_out_")
            self.ctx = RunnerContextBuilder(self.ctx).with_env(
                {
                    "RUNNER_OUTPUTS": str(self._outputs_file),
                    "OFX_OUTPUTS": str(self._outputs_file),
                }
            )

        resolve_fields = [
            "name",
            "shell",
            "working_directory",
            "log_stdout",
            "log_command",
            "env",
            "run_if",
        ]
        match self._run_type:
            case RunType.WORKFLOW:
                resolve_fields.extend(["uses"])
            case RunType.SCRIPT:
                resolve_fields.extend(["script"])
            case RunType.COMMAND:
                resolve_fields.extend(["run"])
            case RunType.SCRIPT_FILE:
                resolve_fields.extend(["script_file"])
            case RunType.TASK:
                resolve_fields.extend(["task", "run_with"])
            case RunType.PIPE:
                pass
        await self._resolve_template_fields(resolve_fields)

        await self._resolve_timeout_field()

        if not self._evaluate_run_if(self.model.run_if, self._run_if_context()):
            self._state_machine.transition(RunnerStatus.CANCELED)
            raise ConditionNotMetError("Step skipped due to run_if condition")

        self.ctx = RunnerContextBuilder(self.ctx).with_env(self.model.env)
        resolved_run_with = await self._resolve_template(self.model.run_with)
        if resolved_run_with:
            self.ctx = RunnerContextBuilder(self.ctx).with_inputs(resolved_run_with)
        await self.reg_set(
            RunnerRegistryKeys.MODEL,
            self.model.model_dump(exclude={"env", "secrets", "run_with"}),
        )

    async def _on_failure_cleanup(self) -> None:
        return await super()._on_failure_cleanup()

    def _create_runner(self) -> BaseRunner:
        return self._step_executor.create_runner(self)

    def _save_output_file(self, stdout: str, outputs: dict) -> None:
        from ofx.runner.core.step_output import save_output_file

        if not self.ctx.output_path:
            self._log_warning("No output_path configured, skipping log file save.")
            return
        if not self.parent:
            return
        save_output_file(
            self.ctx.output_path,
            self.parent.model.jid,
            self.model,
            stdout,
            outputs,
            log_fn=self._log_info,
        )

    def _log_timeline(self, result: RunResult, status: str) -> None:
        from ofx.runner.execution.timeline import log_step

        params = self._build_timeline_params(result)

        log_step(
            ctx_vars=self.ctx.vars,
            output_path=self.ctx.output_path,
            step_name=self.model.name or f"step{self.model.step_index}",
            status=status,
            duration_ms=self.duration_ms(),
            exit_code=result.outputs.get("exit_code"),
            **params,
        )

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        step_idx = getattr(self.model, "step_index", "?")
        prefix = LogContext(step_index=step_idx).prefix
        msg = f"{prefix} › {message_str}" if prefix else message_str
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    def _resolve_working_dir(self) -> Path:
        step = self.model
        step_path = Path(step.working_directory)
        if step_path.is_absolute():
            return step_path

        base_path = self.ctx.vars.get("working_directory", Path.cwd())
        return (base_path / step_path).resolve()

    def _resolve_store_creds(self) -> bool:
        from ofx.runner.core.credential_store import should_store_creds

        parent_model = self.parent.model if self.parent else None
        return should_store_creds(self.model.store_creds, parent_model)
