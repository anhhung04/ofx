"""Job runner for orchestrating step execution"""

import asyncio
import itertools
import logging
from typing import Any

from ofx.models.config import DefaultConfig
from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.context import RunnerContextBuilder
from ofx.runner.core import (
    BaseRunner,
    RunContext,
    RunnerRegistryKeys,
    RunnerStatus,
    RunResult,
)
from ofx.runner.execution.error_helpers import job_step_failed
from ofx.runner.execution.execution_results import (
    JobExecutionResult,
    StepExecutionResult,
)
from ofx.runner.execution.step import StepRunner
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class JobRunner(BaseRunner[Job]):
    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
    ):
        super().__init__(job, ctx, parent, parent.registry)

    async def _pre_run(self) -> None:
        await self._resolve_template_fields(
            ["name", "needs", "run_if", "env", "defaults"]
        )
        self.ctx = RunnerContextBuilder(self.ctx).with_env(self.model.env)
        self._log_debug(f"Resolved job: {self.model.model_dump(exclude={'steps'})}")

        if isinstance(self.model.needs, str):
            self.model.needs = [self.model.needs]

        runners: dict[str, BaseRunner] = self.parent.runners  # type: ignore
        dep_runners = []
        for job_id in self.model.needs:
            runner = runners.get(job_id)
            if not runner:
                raise RuntimeError(
                    f"Job dependency '{job_id}' is missing from workflow runners."
                )
            dep_runners.append(runner)

        run_if_expr = self.model.run_if
        if run_if_expr is True and dep_runners:
            run_if_expr = "success()"

        if not self._evaluate_run_if(run_if_expr, self._run_if_context(dep_runners)):
            self._state_machine.transition(RunnerStatus.CANCELED)
            raise Exception(self._produce_log("Job condition is not met"))

        job_default_config = self.model.defaults.model_dump(exclude_defaults=True)
        workflow_default_config = self.parent.model.defaults.model_dump()  # type: ignore
        for key, value in job_default_config.items():
            workflow_default_config[key] = value
        self.model.defaults = DefaultConfig.model_validate(workflow_default_config)

        await self.reg_set(
            RunnerRegistryKeys.MODEL,
            self.model.model_dump(exclude={"steps", "env"}),
        )

    async def _do_run(self) -> None:
        self._log_info(f"Starting job '{self.model.name or self.model.jid}'")
        for step in self.model.steps:
            step_ctx = self._child_context(
                update={
                    "secrets": self.ctx.secrets if step.secrets != "inherit" else {},
                },
            )

            step_runner = StepRunner(
                step,
                step_ctx,
                self,
            )
            step_runner.log_level = logging.CRITICAL
            self._runners[str(step.step_index)] = step_runner
            result = await step_runner.run()
            if step_runner.is_failed and not step.continue_on_error:
                raise RuntimeError(
                    job_step_failed(step.name or step.step_index, result.error)
                )

    async def _post_run(self) -> None:
        # Handle job outputs
        if self.model.outputs:
            resolved_outputs = {}
            for key, value in self.model.outputs.items():
                resolved_value = await self._resolve_template(value)
                resolved_outputs[key] = resolved_value
            await self.reg_update(RunnerRegistryKeys.OUTPUTS, resolved_outputs)

        step_results: list[dict[str, Any]] = []
        failed_steps: list[int] = []
        for runner in self._runners.values():
            if not isinstance(runner, StepRunner):
                continue
            step_result = await runner.get_result()
            run_type = (
                runner._run_type.value
                if hasattr(runner, "_run_type")
                else runner.model.get_run_type().value
            )
            step_exec = StepExecutionResult(
                step_index=runner.model.step_index,
                name=runner.model.name,
                run_type=run_type,
                status=step_result.status.value,
                error=step_result.error,
                outputs=step_result.outputs,
            )
            step_results.append(step_exec.to_dict())
            if step_result.status == RunnerStatus.FAILED:
                failed_steps.append(runner.model.step_index)

        status_value = (
            RunnerStatus.COMPLETED.value
            if self.status == RunnerStatus.FINISHED
            else self.status.value
        )
        job_exec = JobExecutionResult(
            jid=self.model.jid,
            name=self.model.name,
            status=status_value,
            error=self._error,
            total_steps=len(self.model.steps),
            failed_steps=failed_steps,
            steps=step_results,
            duration_ms=self.duration_ms(),
        )
        await self.reg_set(RunnerRegistryKeys.EXECUTION, job_exec.to_dict())

        self._log_debug(
            f"job '{self.model.name or self.model.jid}' result: {await self.get_result()}"
        )

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        msg = f"'{self.model.jid}' › {message_str}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    @property
    def total_steps(self) -> int:
        return len(self.model.steps)

    def _run_if_context(self, dep_runners: list[BaseRunner]) -> dict[str, Any]:
        if not dep_runners:
            return {
                "success": lambda: True,
                "failure": lambda: False,
                "canceled": lambda: False,
                "always": lambda: True,
            }
        return {
            "success": lambda: all(r.is_success for r in dep_runners),
            "failure": lambda: any(r.is_failed for r in dep_runners),
            "canceled": lambda: any(
                r.status == RunnerStatus.CANCELED for r in dep_runners
            ),
            "always": lambda: True,
        }


class MatrixJobRunner(BaseRunner[Job]):
    """Runner for jobs with matrix strategy, handling multiple matrix combinations"""

    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
    ):
        super().__init__(job, ctx, parent)
        self.name = f"Matrix{self.name}"

    async def _do_run(self) -> None:
        """Run all matrix combinations with optional parallelism limit"""
        if not self._matrix_combinations:
            self._state_machine.transition(RunnerStatus.COMPLETED)
            return

        strategy = self.model.strategy
        max_parallel = (
            strategy.max_parallel if strategy else len(self._matrix_combinations)
        )

        semaphore = asyncio.Semaphore(max_parallel)

        async def run_instance(matrix_idx: int, matrix_values: dict[str, Any]):
            async with semaphore:
                return await self._run_single_job(matrix_idx, matrix_values)

        tasks = [
            asyncio.create_task(run_instance(idx, combo))
            for idx, combo in enumerate(self._matrix_combinations)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        failed = False
        errors = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed = True
                errors.append(f"Matrix combination {i}: {result}")
            elif (
                isinstance(result, RunResult)
                and result.status != RunnerStatus.COMPLETED
            ):
                failed = True
                errors.append(f"Matrix combination {i}: {result.error or 'Failed'}")

        if failed:
            self._state_machine.transition(RunnerStatus.FAILED)
            self._error = "; ".join(errors)
        else:
            self._state_machine.transition(RunnerStatus.COMPLETED)

    async def _run_single_job(self, matrix_idx: int, matrix_values: dict[str, Any]):
        """Run a single job instance with specific matrix values"""
        job_ctx = self._child_context()
        job_ctx.vars["matrix"] = matrix_values
        new_jid = f"{self.model.jid}_{str(matrix_idx)}"
        runner = JobRunner(
            self.model.model_copy(
                update={
                    "name": f"{self.model.name}{{{str(matrix_idx)}}}",
                    "jid": new_jid,
                    "matrix_values": matrix_values,
                    "matrix_index": matrix_idx,
                },
            ),
            job_ctx,
            parent=self.parent,  # type: ignore
        )
        self._runners[new_jid] = runner
        return await runner.run()

    async def _pre_run(self) -> None:
        await self._resolve_template_fields(["strategy"])
        self._matrix_combinations = self._generate_matrix_combinations()

    async def _post_run(self) -> None:
        pass

    def _generate_matrix_combinations(self) -> list[dict[str, Any]]:
        """Generate all matrix combinations with include/exclude rules"""
        strategy = self.model.strategy
        if not strategy or not strategy.matrix:
            return []

        matrix_keys = list(strategy.matrix.keys())
        matrix_values = [strategy.matrix[key] for key in matrix_keys]

        base_combinations = [
            dict(zip(matrix_keys, combination, strict=True))
            for combination in itertools.product(*matrix_values)
        ]

        def _matches_matrix_filter(
            combo: dict[str, Any], filters: list[dict[str, Any]]
        ) -> bool:
            """Check if a combination matches any filter"""
            for filter_dict in filters:
                if all(combo.get(key) == value for key, value in filter_dict.items()):
                    return True
            return False

        if strategy.exclude:
            base_combinations = [
                combo
                for combo in base_combinations
                if not _matches_matrix_filter(combo, strategy.exclude)
            ]

        if strategy.include:
            for include_combo in strategy.include:
                if include_combo not in base_combinations:
                    base_combinations.append(include_combo)

        return base_combinations
