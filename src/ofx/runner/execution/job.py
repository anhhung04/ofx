"""Job runner for orchestrating step execution"""

import asyncio
import logging
from typing import Any

from ofx.models.config import DefaultConfig
from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.context import RunnerContextBuilder
from ofx.runner.core import (
    BaseRunner,
    ConditionNotMetError,
    RunContext,
    RunnerRegistryKeys,
    RunnerStatus,
    RunResult,
)
from ofx.runner.execution.error_helpers import job_step_failed
from ofx.runner.execution.execution_results import (
    build_job_execution_result,
    build_run_if_context,
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

        if not self._evaluate_run_if(run_if_expr, build_run_if_context(dep_runners)):
            self._state_machine.transition(RunnerStatus.CANCELED)
            raise ConditionNotMetError(self._produce_log("Job condition is not met"))

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
        resolved_outputs = await self._resolve_job_outputs()
        if resolved_outputs:
            await self.reg_update(RunnerRegistryKeys.OUTPUTS, resolved_outputs)

        job_exec = build_job_execution_result(self, self._runners)
        await self.reg_set(RunnerRegistryKeys.EXECUTION, job_exec.to_dict())

        # Clean up non-exported task temp files that were kept for
        # subsequent steps (export_output=False tasks).
        await self._cleanup_temp_task_files()

    async def _cleanup_temp_task_files(self) -> None:
        """Remove temp output files from non-exported tasks after all steps finish."""
        from pathlib import Path

        for step_runner in self._runners.values():
            try:
                result = await step_runner.get_result()
                output_file = result.outputs.get("output_file", "")
                if output_file and ".ofx_task_" in output_file:
                    p = Path(output_file)
                    if p.exists():
                        p.unlink(missing_ok=True)
            except Exception:
                pass

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        msg = f"'{self.model.jid}' › {message_str}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    @property
    def total_steps(self) -> int:
        return len(self.model.steps)


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

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        msg = f"'{self.model.jid}' › {message_str}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    async def _do_run(self) -> None:
        """Run all matrix combinations with optional parallelism limit"""
        if not self._matrix_combinations:
            return

        strategy = self.model.strategy
        max_parallel = (
            strategy.max_parallel if strategy else len(self._matrix_combinations)
        )
        fail_fast = strategy.fail_fast if strategy else True

        semaphore = asyncio.Semaphore(max_parallel)
        failed_event = asyncio.Event()

        async def run_instance(matrix_idx: int, matrix_values: dict[str, Any]):
            if fail_fast and failed_event.is_set():
                return None
            async with semaphore:
                if fail_fast and failed_event.is_set():
                    return None
                try:
                    return await self._run_single_job(matrix_idx, matrix_values)
                except Exception:
                    if fail_fast:
                        failed_event.set()
                    raise

        tasks = [
            asyncio.create_task(run_instance(idx, combo))
            for idx, combo in enumerate(self._matrix_combinations)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors = []
        for i, result in enumerate(results):
            combo = self._matrix_combinations[i]
            combo_label = ", ".join(f"{k}={v}" for k, v in combo.items())
            if isinstance(result, Exception):
                errors.append(f"Combination {i} ({combo_label}): {result}")
            elif (
                isinstance(result, RunResult)
                and result.status != RunnerStatus.COMPLETED
            ):
                errors.append(
                    f"Combination {i} ({combo_label}): {result.error or 'Failed'}"
                )

        if errors:
            raise RuntimeError("; ".join(errors))

    async def _run_single_job(self, matrix_idx: int, matrix_values: dict[str, Any]):
        """Run a single job instance with specific matrix values"""
        job_ctx = self._child_context()
        if self.model.strategy:
            job_ctx.vars["strategy"] = self.model.strategy.model_dump()
        job_ctx.vars["matrix"] = matrix_values

        # Propagate auto-expanded matrix values back into inputs so that
        # {{ inputs.target }} resolves to the current matrix target value.
        for key in job_ctx.vars.get("_matrix_input_keys", []):
            if key in matrix_values:
                job_ctx.inputs[key] = matrix_values[key]

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
            parent=self.parent,  # type: ignore
        )
        self._runners[new_jid] = runner
        return await runner.run()

    async def _pre_run(self) -> None:
        await self._resolve_template_fields(["strategy"])
        # After template resolution, matrix values that were template strings
        # may now be JSON-encoded list strings — parse them into real lists.
        if self.model.strategy and self.model.strategy.matrix:
            import json

            for key, val in self.model.strategy.matrix.items():
                if isinstance(val, str):
                    try:
                        parsed = json.loads(val)
                        if isinstance(parsed, list):
                            self.model.strategy.matrix[key] = parsed
                            logger.debug(
                                self._produce_log(
                                    f"Matrix key '{key}' resolved to {len(parsed)} item(s)"
                                )
                            )
                        else:
                            self.model.strategy.matrix[key] = [parsed]
                    except (json.JSONDecodeError, ValueError):
                        # Wrap scalar string as single-element list
                        self.model.strategy.matrix[key] = [val]
        self._matrix_combinations = self._generate_matrix_combinations()

    async def _post_run(self) -> None:
        pass

    def _generate_matrix_combinations(self) -> list[dict[str, Any]]:
        """Generate all matrix combinations with include/exclude rules."""
        from ofx.runner.core.matrix_utils import generate_matrix_combinations

        strategy = self.model.strategy
        if not strategy or not strategy.matrix:
            return []

        # Detect empty source lists before expansion so the warning is accurate.
        empty_keys = [k for k, v in strategy.matrix.items() if isinstance(v, list) and len(v) == 0]
        if empty_keys:
            self._log_warning(
                f"Matrix produced 0 combinations: key(s) {empty_keys} resolved to an empty list. "
                "Check that upstream job outputs are non-empty."
            )
            return []

        combos = generate_matrix_combinations(
            strategy.matrix,
            include=strategy.include,
            exclude=strategy.exclude,
            enforce_limit=True,
        )

        if not combos:
            self._log_warning(
                "Matrix produced 0 combinations after include/exclude filtering"
            )

        return combos
