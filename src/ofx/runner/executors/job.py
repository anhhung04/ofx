"""Executors for job and matrix job runners."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ofx.runner.core.models import RunnerStatus, RunResult
from ofx.runner.core.registry_keys import RunnerRegistryKeys
from ofx.runner.executors import Executor
class JobExecutor(Executor):
    async def pre_run(self, runner) -> None:
        return None

    async def do_run(self, runner) -> None:
        runner._log_info(f"Starting job '{runner.model.name or runner.model.jid}'")
        for step in runner.model.steps:
            step_ctx = runner._child_context(
                update={
                    "secrets": runner.ctx.secrets if step.secrets != "inherit" else {},
                },
            )

            from ofx.runner.execution.step import StepRunner

            step_runner = StepRunner(step, step_ctx, runner)
            step_runner.log_level = logging.CRITICAL
            runner._runners[str(step.step_index)] = step_runner
            result = await step_runner.run()
            if step_runner.is_failed and not step.continue_on_error:
                raise RuntimeError(
                    self._job_step_failed(step.name or step.step_index, result.error)
                )

    async def post_run(self, runner) -> None:
        await self._save_job_results(runner)
        await self._cleanup_temp_task_files(runner)

    async def _save_job_results(self, runner) -> None:
        resolved_outputs = await runner._resolve_job_outputs()
        if resolved_outputs:
            await runner.reg_update(RunnerRegistryKeys.OUTPUTS, resolved_outputs)

        from ofx.runner.execution.execution_results import build_job_execution_result

        job_exec = build_job_execution_result(runner, runner._runners)
        await runner.reg_set(RunnerRegistryKeys.EXECUTION, job_exec.to_dict())

    def _job_step_failed(self, step_name, error) -> str:
        from ofx.runner.execution.error_helpers import job_step_failed

        return job_step_failed(step_name, error)

    def check_dependencies_and_run_if(self, runner) -> None:
        if isinstance(runner.model.needs, str):
            runner.model.needs = [runner.model.needs]

        runners = runner.parent.runners
        dep_runners = []
        for job_id in runner.model.needs:
            dep_runner = runners.get(job_id)
            if not dep_runner:
                raise RuntimeError(
                    f"Job dependency '{job_id}' is missing from workflow runners."
                )
            dep_runners.append(dep_runner)

        run_if_expr = runner.model.run_if
        if run_if_expr is True and dep_runners:
            run_if_expr = "success()"

        from ofx.runner.core.models import ConditionNotMetError
        from ofx.runner.execution.execution_results import build_run_if_context

        if not runner._evaluate_run_if(
            run_if_expr, build_run_if_context(dep_runners)
        ):
            runner._state_machine.transition(RunnerStatus.CANCELED)
            raise ConditionNotMetError(runner._produce_log("Job condition is not met"))

    async def _cleanup_temp_task_files(self, runner) -> None:
        for step_runner in runner._runners.values():
            try:
                result = await step_runner.get_result()
                output_file = result.outputs.get("output_file", "")
                if output_file and ".ofx_task_" in output_file:
                    path = Path(output_file)
                    if path.exists():
                        path.unlink(missing_ok=True)
            except Exception:
                runner._log_debug(
                    f"Job '{runner.model.jid}': failed to clean up temp task file"
                )


class MatrixExecutor(Executor):
    async def pre_run(self, runner) -> None:
        return None

    async def do_run(self, runner) -> None:
        if not runner._matrix_combinations:
            return

        strategy = runner.model.strategy
        max_parallel = (
            strategy.max_parallel if strategy else len(runner._matrix_combinations)
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
                    return await runner._run_single_job(matrix_idx, matrix_values)
                except Exception:
                    if fail_fast:
                        failed_event.set()
                    raise

        tasks = [
            asyncio.create_task(run_instance(idx, combo))
            for idx, combo in enumerate(runner._matrix_combinations)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors = []
        for idx, result in enumerate(results):
            combo = runner._matrix_combinations[idx]
            combo_label = ", ".join(f"{k}={v}" for k, v in combo.items())
            if isinstance(result, Exception):
                errors.append(f"Combination {idx} ({combo_label}): {result}")
            elif isinstance(result, RunResult) and result.status != RunnerStatus.COMPLETED:
                errors.append(
                    f"Combination {idx} ({combo_label}): {result.error or 'Failed'}"
                )

        if errors:
            detail = "\n  ".join(errors[:10])
            suffix = (
                f"\n  ... and {len(errors) - 10} more" if len(errors) > 10 else ""
            )
            raise RuntimeError(
                f"Matrix job '{runner.model.jid}' failed ({len(errors)} combination(s)):\n  {detail}{suffix}"
            )

    async def post_run(self, runner) -> None:
        return None

    def generate_matrix_combinations(self, runner) -> list[dict[str, Any]]:
        strategy = runner.model.strategy
        if not strategy or not strategy.matrix:
            return []

        empty_keys = [
            key
            for key, value in strategy.matrix.items()
            if isinstance(value, list) and len(value) == 0
        ]
        if empty_keys:
            runner._log_warning(
                f"Matrix produced 0 combinations: key(s) {empty_keys} resolved to an empty list. "
                "Check that upstream job outputs are non-empty."
            )
            return []

        from ofx.runner.core.matrix_utils import generate_matrix_combinations

        combos = generate_matrix_combinations(
            {
                key: ([value] if not isinstance(value, list) else value)
                for key, value in strategy.matrix.items()
            },
            include=strategy.include,
            exclude=strategy.exclude,
            enforce_limit=True,
        )

        if not combos:
            runner._log_warning(
                "Matrix produced 0 combinations after include/exclude filtering"
            )

        return combos
