"""Executor for matrix job expansion and orchestration."""

from __future__ import annotations

import json
from typing import Any

from ofx.runner.context import RunnerContextBuilder, RunnerStatus, RunResult
from ofx.runner.executors.base import Executor
from ofx.runner.executors.parallel import run_limited_fail_fast


class MatrixExecutor(Executor):
    async def pre_run(self, runner) -> None:
        await runner._resolve_template_fields(["strategy"])
        if runner.model.strategy and runner.model.strategy.matrix:
            for key, val in runner.model.strategy.matrix.items():
                if isinstance(val, str):
                    try:
                        parsed = json.loads(val)
                        if isinstance(parsed, list):
                            runner.model.strategy.matrix[key] = parsed
                            runner._log_debug(
                                f"Matrix key '{key}' resolved to {len(parsed)} item(s)"
                            )
                        else:
                            runner.model.strategy.matrix[key] = [parsed]
                    except (json.JSONDecodeError, ValueError):
                        runner.model.strategy.matrix[key] = [val]
        runner._matrix_combinations = self.generate_matrix_combinations(runner)

    async def do_run(self, runner) -> None:
        if not runner._matrix_combinations:
            return

        strategy = runner.model.strategy
        max_parallel = (
            strategy.max_parallel if strategy else len(runner._matrix_combinations)
        )
        fail_fast = strategy.fail_fast if strategy else True

        results = await run_limited_fail_fast(
            runner._matrix_combinations,
            max_parallel=max_parallel,
            fail_fast=fail_fast,
            run_item=lambda idx, combo: self.run_single_job(runner, idx, combo),
            is_failure=lambda result: isinstance(result, RunResult)
            and result.status != RunnerStatus.COMPLETED,
        )

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

    async def run_single_job(
        self,
        runner,
        matrix_idx: int,
        matrix_values: dict[str, Any],
    ):
        job_ctx = runner._child_context()
        vars_update: dict[str, Any] = {"matrix": matrix_values}
        if runner.model.strategy:
            vars_update["strategy"] = runner.model.strategy.model_dump()
        job_ctx = RunnerContextBuilder(job_ctx).with_vars(vars_update)

        matrix_input_updates = {
            key: matrix_values[key]
            for key in job_ctx.vars.get("_matrix_input_keys", [])
            if key in matrix_values
        }
        if matrix_input_updates:
            job_ctx = RunnerContextBuilder(job_ctx).with_inputs(matrix_input_updates)

        from ofx.runner.job import JobRunner, clone_indexed_job

        job_copy = clone_indexed_job(
            runner.model,
            matrix_idx,
            matrix_values,
        )
        child_runner = JobRunner(
            job_copy,
            job_ctx,
            parent=runner.parent,  # type: ignore[arg-type]
        )
        runner._runners[job_copy.jid] = child_runner
        return await child_runner.run()

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

        from ofx.runner.matrix_utils import generate_matrix_combinations

        combos = generate_matrix_combinations(
            strategy.matrix,
            include=strategy.include,
            exclude=strategy.exclude,
            enforce_limit=True,
        )

        if not combos:
            runner._log_warning(
                "Matrix produced 0 combinations after include/exclude filtering"
            )

        return combos
