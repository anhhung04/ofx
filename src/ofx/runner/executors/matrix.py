"""Executor for matrix job expansion and orchestration."""

from __future__ import annotations

import json
from typing import Any

from ofx.runner.context import RunResult
from ofx.runner.executors.base import Executor
from ofx.runner.executors.parallel import (
    parallel_run_settings,
    run_parallel_runner_items,
)


class MatrixExecutor(Executor):
    async def pre_run(self, runner) -> None:
        await runner._resolve_template_fields(["strategy"])
        if runner.model.strategy and runner.model.strategy.matrix:
            for key, val in runner.model.strategy.matrix.items():
                if not isinstance(val, str):
                    continue

                try:
                    normalized = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    normalized = val
                if isinstance(normalized, list):
                    runner.model.strategy.matrix[key] = normalized
                    runner._log_debug(
                        f"Matrix key '{key}' resolved to {len(normalized)} item(s)"
                    )
                else:
                    runner.model.strategy.matrix[key] = [normalized]
        runner._matrix_combinations = self.generate_matrix_combinations(runner)

    async def do_run(self, runner) -> None:
        if not runner._matrix_combinations:
            return

        max_parallel, fail_fast = parallel_run_settings(
            runner.model.strategy,
            item_count=len(runner._matrix_combinations),
        )

        errors = await run_parallel_runner_items(
            runner._matrix_combinations,
            max_parallel=max_parallel,
            fail_fast=fail_fast,
            run_item=lambda idx, combo: self.run_single_job(runner, idx, combo),
            describe_item=lambda idx, combo: (
                f"Combination {idx} ({', '.join(f'{key}={value}' for key, value in combo.items())})"
            ),
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
        matrix_input_updates = {
            key: matrix_values[key]
            for key in runner.ctx.vars.get("_matrix_input_keys", [])
            if key in matrix_values
        }

        from ofx.runner.job import JobRunner, attach_indexed_job_runner, build_indexed_job_context

        job_ctx = build_indexed_job_context(
            runner,
            vars_update={"matrix": matrix_values},
            input_updates=matrix_input_updates,
        )

        _job_copy, child_runner = attach_indexed_job_runner(
            runner,
            ctx=job_ctx,
            index=matrix_idx,
            values=matrix_values,
            runner_cls=JobRunner,
        )
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
