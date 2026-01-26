"""Workflow execution manager for running scheduled stages."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import itertools

from ofx.runner.execution.job import JobRunner, MatrixJobRunner
from ofx.runner.execution.step import StepRunner


@dataclass
class StageResult:
    errors: list[str]


@dataclass
class ExecutionResult:
    errors: list[str] = field(default_factory=list)
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
            stage_errors, failed_jobs = await self._run_stage(
                stage_index, stage_runners
            )
            if stage_errors:
                result.failed_stage_indices.append(stage_index)
                result.errors.extend(stage_errors)
                result.failed_job_ids.extend(failed_jobs)
        return result

    def _build_stage_runners(
        self, stage: list[str], staged_jobs: dict
    ) -> dict[str, JobRunner | MatrixJobRunner]:
        stage_runners: dict[str, JobRunner | MatrixJobRunner] = {}
        for job_id in stage:
            job = staged_jobs[job_id]
            job_ctx = self._parent._child_context(
                update={"allow_interactive": len(stage) == 1}
            )
            if job.strategy and job.strategy.matrix:
                runner = MatrixJobRunner(job, job_ctx, parent=self._parent)
            else:
                runner = JobRunner(job, job_ctx, parent=self._parent)
            stage_runners[job_id] = runner
            self._parent._runners[job_id] = runner
        return stage_runners

    async def _run_stage(
        self,
        stage_index: int,
        stage_runners: dict[str, JobRunner | MatrixJobRunner],
    ) -> tuple[list[str], list[str]]:
        job_ids = list(stage_runners.keys())
        coros = [stage_runners[job_id].run() for job_id in job_ids]
        results = await asyncio.gather(*coros, return_exceptions=True)
        errors: list[str] = []
        failed_jobs: list[str] = []
        for job_id, runner, result in zip(
            job_ids, stage_runners.values(), results, strict=False
        ):
            job_result = await runner.get_result()
            if isinstance(result, Exception):
                errors.append(f"{job_id}: {result}")
                failed_jobs.append(job_id)
            elif not runner.is_success:
                error = job_result.error or "Unknown error"
                errors.append(f"job '{job_id}': {error}")
                failed_jobs.append(job_id)
        if errors:
            self._parent._log_stage_failure(stage_index, errors)
        return errors, failed_jobs

    def _matrix_combo_count(self, runner: MatrixJobRunner) -> int:
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
