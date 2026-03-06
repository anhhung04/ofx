"""Workflow execution manager for running scheduled stages."""

from __future__ import annotations

import asyncio
import itertools
from dataclasses import dataclass, field

from ofx.runner.core import BaseRunner
from ofx.runner.execution.runner_factory import create_job_runner


@dataclass
class ExecutionResult:
    failed_job_ids: list[str] = field(default_factory=list)
    failed_stage_indices: list[int] = field(default_factory=list)


class WorkflowExecutionManager:
    """Executes workflow stages and aggregates errors."""

    def __init__(self, parent_runner):
        self._parent = parent_runner

    async def run(self, schedule: list[list[str]], staged_jobs: dict):
        result = ExecutionResult()
        for stage_index, stage in enumerate(schedule):
            stage_runners = self._build_stage_runners(stage, staged_jobs)
            failed_jobs = await self._run_stage(stage_index, stage_runners)
            if failed_jobs:
                result.failed_stage_indices.append(stage_index)
                result.failed_job_ids.extend(failed_jobs)
        return result

    def _build_stage_runners(
        self, stage: list[str], staged_jobs: dict
    ) -> dict[str, BaseRunner]:
        stage_runners: dict[str, BaseRunner] = {}
        for job_id in stage:
            job = staged_jobs[job_id]
            job_ctx = self._parent._child_context(
                update={"allow_interactive": len(stage) == 1}
            )
            runner = create_job_runner(job, job_ctx, parent=self._parent)
            stage_runners[job_id] = runner
            self._parent._runners[job_id] = runner
        return stage_runners

    async def _run_stage(
        self,
        stage_index: int,
        stage_runners: dict[str, BaseRunner],
    ) -> list[str]:
        self._parent._log_info(
            f"Starting stage {stage_index + 1} with jobs: {list(stage_runners.keys())}"
        )
        job_ids = list(stage_runners.keys())
        tasks = {
            job_id: asyncio.create_task(stage_runners[job_id].run())
            for job_id in job_ids
        }
        failed_jobs: list[str] = []
        while tasks:
            done, _ = await asyncio.wait(
                tasks.values(), timeout=0.01, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                job_id = next(jid for jid, t in tasks.items() if t is task)
                runner = stage_runners[job_id]
                try:
                    task.result()
                except Exception:
                    pass  # Error is captured in runner._error
                if runner.is_failed:
                    failed_jobs.append(job_id)
                del tasks[job_id]
        return failed_jobs

    def _matrix_combo_count(self, runner) -> int:
        strategy = runner.model.strategy
        if not strategy or not strategy.matrix:
            return 1
        matrix_keys = list(strategy.matrix.keys())
        matrix_values = [strategy.matrix[key] for key in matrix_keys]
        base_combos = [
            dict(zip(matrix_keys, combination, strict=True))
            for combination in itertools.product(*matrix_values)
        ]

        def _matches_matrix_filter(
            combo: dict, filters: list[dict[str, object]]
        ) -> bool:
            for filter_dict in filters:
                if all(combo.get(key) == value for key, value in filter_dict.items()):
                    return True
            return False

        if strategy.exclude:
            base_combos = [
                combo
                for combo in base_combos
                if not _matches_matrix_filter(combo, strategy.exclude)
            ]
        if strategy.include:
            for include_combo in strategy.include:
                if include_combo not in base_combos:
                    base_combos.append(include_combo)
        return max(len(base_combos), 1)
