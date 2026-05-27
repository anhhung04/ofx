"""Job runners delegating orchestration to executor classes."""

from __future__ import annotations

from typing import Any

from ofx.models.config import DefaultConfig
from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.context import RunnerContextBuilder
from ofx.runner.core import BaseRunner, RunContext, RunnerRegistryKeys
from ofx.runner.executors.job import JobExecutor, MatrixExecutor
from ofx.runner.logging import LogContext


class JobRunner(BaseRunner[Job]):
    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
        executor: JobExecutor | None = None,
    ):
        job_executor = executor or JobExecutor()
        self._job_executor: JobExecutor = job_executor
        super().__init__(
            job,
            ctx,
            parent,
            parent.registry,
            executor=job_executor,
        )

    async def _pre_run(self) -> None:
        await self._resolve_template_fields(
            ["name", "needs", "run_if", "env", "defaults"]
        )
        self.ctx = RunnerContextBuilder(self.ctx).with_env(self.model.env)
        self._log_debug(f"Resolved job: {self.model.model_dump(exclude={'steps'})}")

        self._job_executor.check_dependencies_and_run_if(self)

        job_default_config = self.model.defaults.model_dump(exclude_defaults=True)
        workflow_default_config = self.parent.model.defaults.model_dump()  # type: ignore[union-attr]
        for key, value in job_default_config.items():
            workflow_default_config[key] = value
        self.model.defaults = DefaultConfig.model_validate(workflow_default_config)

        await self.reg_set(
            RunnerRegistryKeys.MODEL,
            self.model.model_dump(exclude={"steps", "env"}),
        )

    async def _save_job_results(self) -> None:
        await self._job_executor._save_job_results(self)

    async def _cleanup_temp_task_files(self) -> None:
        await self._job_executor._cleanup_temp_task_files(self)

    @property
    def total_steps(self) -> int:
        return len(self.model.steps)

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        prefix = LogContext(model_jid=self.model.jid).prefix
        msg = f"{prefix} › {message_str}" if prefix else message_str
        if self.parent:
            return self.parent._produce_log(msg)
        return msg


class MatrixJobRunner(BaseRunner[Job]):
    """Runner for jobs with matrix strategy, handling multiple combinations."""

    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
        executor: MatrixExecutor | None = None,
    ):
        matrix_executor = executor or MatrixExecutor()
        self._matrix_executor: MatrixExecutor = matrix_executor
        super().__init__(job, ctx, parent, executor=matrix_executor)
        self.name = f"Matrix{self.name}"

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        prefix = LogContext(model_jid=self.model.jid).prefix
        msg = f"{prefix} › {message_str}" if prefix else message_str
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    async def _run_single_job(self, matrix_idx: int, matrix_values: dict[str, Any]):
        job_ctx = self._child_context()
        vars_update: dict[str, Any] = {"matrix": matrix_values}
        if self.model.strategy:
            vars_update["strategy"] = self.model.strategy.model_dump()
        job_ctx = RunnerContextBuilder(job_ctx).with_vars(vars_update)

        matrix_input_updates = {
            key: matrix_values[key]
            for key in job_ctx.vars.get("_matrix_input_keys", [])
            if key in matrix_values
        }
        if matrix_input_updates:
            job_ctx = RunnerContextBuilder(job_ctx).with_inputs(matrix_input_updates)

        new_jid = f"{self.model.jid}_{str(matrix_idx)}"
        runner = JobRunner(
            self.model.model_copy(
                deep=True,
                update={
                    "name": f"[{self.model.name}]{{{str(matrix_idx)}}}",
                    "jid": new_jid,
                    "matrix_values": matrix_values,
                    "matrix_index": matrix_idx,
                },
            ),
            job_ctx,
            parent=self.parent,  # type: ignore[arg-type]
        )
        self._runners[new_jid] = runner
        return await runner.run()

    async def _pre_run(self) -> None:
        await self._resolve_template_fields(["strategy"])
        if self.model.strategy and self.model.strategy.matrix:
            import json

            for key, val in self.model.strategy.matrix.items():
                if isinstance(val, str):
                    try:
                        parsed = json.loads(val)
                        if isinstance(parsed, list):
                            self.model.strategy.matrix[key] = parsed
                            self._log_debug(
                                f"Matrix key '{key}' resolved to {len(parsed)} item(s)"
                            )
                        else:
                            self.model.strategy.matrix[key] = [parsed]
                    except (json.JSONDecodeError, ValueError):
                        self.model.strategy.matrix[key] = [val]
        self._matrix_combinations = self._matrix_executor.generate_matrix_combinations(self)
