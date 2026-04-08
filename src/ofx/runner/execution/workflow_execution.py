"""Workflow execution manager for running scheduled stages."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from ofx.runner.core import BaseRunner
from ofx.runner.execution.runner_factory import create_job_runner
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


def _memory_usage_percent() -> float:
    """Return system memory usage as a percentage (0-100).

    Uses ``/proc/meminfo`` on Linux for a zero-dependency check.
    Falls back to 0.0 (disabled) on unsupported platforms.
    """
    try:
        with open("/proc/meminfo") as f:
            info: dict[str, int] = {}
            for line in f:
                parts = line.split()
                if parts[0] in ("MemTotal:", "MemAvailable:"):
                    info[parts[0].rstrip(":")] = int(parts[1])
                    if len(info) == 2:
                        break
            total = info.get("MemTotal", 0)
            available = info.get("MemAvailable", 0)
            if total > 0:
                return (1 - available / total) * 100
    except (OSError, KeyError, ValueError, ZeroDivisionError):
        pass
    return 0.0


@dataclass
class ExecutionResult:
    failed_job_ids: list[str] = field(default_factory=list)
    failed_stage_indices: list[int] = field(default_factory=list)


class WorkflowExecutionManager:
    """Executes workflow stages and aggregates errors.

    Enforces a global concurrency cap via an ``asyncio.Semaphore`` so
    that at most ``settings.max_parallel_jobs`` jobs run at the same time
    across all stages.  When ``settings.memory_limit_percent > 0``, new
    job launches are delayed if system RAM usage exceeds the threshold.
    """

    def __init__(self, parent_runner):
        self._parent = parent_runner
        max_j = settings.max_parallel_jobs
        self._job_semaphore = asyncio.Semaphore(max_j)
        self._mem_limit = settings.memory_limit_percent

    async def run(self, schedule: list[list[str]], staged_jobs: dict):
        result = ExecutionResult()
        for stage_index, stage in enumerate(schedule):
            # Check time window guard between stages
            time_guard = getattr(self._parent, "_time_guard", None)
            if time_guard and time_guard.should_abort:
                remaining_ids = [
                    jid for s in schedule[stage_index:] for jid in s
                ]
                result.failed_job_ids.extend(remaining_ids)
                result.failed_stage_indices.append(stage_index)
                self._parent._log_error(
                    "🛑 Time window expired — aborting remaining stages"
                )
                break

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

    # ------------------------------------------------------------------
    # Memory-pressure backpressure
    # ------------------------------------------------------------------

    async def _wait_for_memory(self) -> None:
        """Block until system memory usage drops below the configured limit.

        Checks every 5 seconds and logs a warning on first detection.
        """
        if self._mem_limit <= 0:
            return
        warned = False
        while True:
            usage = _memory_usage_percent()
            if usage <= 0 or usage < self._mem_limit:
                return
            if not warned:
                logger.warning(
                    "Memory usage %.0f%% exceeds limit %d%% — "
                    "waiting before launching next job",
                    usage,
                    self._mem_limit,
                )
                warned = True
            await asyncio.sleep(5)

    # ------------------------------------------------------------------
    # Stage execution with semaphore
    # ------------------------------------------------------------------

    async def _run_stage(
        self,
        stage_index: int,
        stage_runners: dict[str, BaseRunner],
    ) -> list[str]:
        n_jobs = len(stage_runners)
        max_j = self._job_semaphore._value  # type: ignore[attr-defined]
        self._parent._log_info(
            f"Starting stage {stage_index + 1} with {n_jobs} job(s) "
            f"(concurrency limit: {max_j})"
        )
        job_ids = list(stage_runners.keys())

        async def _guarded_run(job_id: str) -> None:
            """Acquire semaphore, wait for memory, then run the job."""
            async with self._job_semaphore:
                await self._wait_for_memory()
                await stage_runners[job_id].run()

        tasks = {
            job_id: asyncio.create_task(_guarded_run(job_id))
            for job_id in job_ids
        }
        task_to_job = {t: jid for jid, t in tasks.items()}
        failed_jobs: list[str] = []
        try:
            while tasks:
                done, _ = await asyncio.wait(
                    tasks.values(), timeout=0.01, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    job_id = task_to_job[task]
                    runner = stage_runners[job_id]
                    try:
                        task.result()
                    except (asyncio.CancelledError, KeyboardInterrupt):
                        raise
                    except Exception as exc:
                        # Error is captured in runner._error; log for traceability
                        logger.debug("Job '%s' raised: %s", job_id, exc)
                    if runner.is_failed:
                        failed_jobs.append(job_id)
                    del tasks[job_id]
        except (asyncio.CancelledError, KeyboardInterrupt):
            # Cancel remaining tasks on interruption
            for _job_id, task in tasks.items():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
            raise
        return failed_jobs

    def _matrix_combo_count(self, runner) -> int:
        from ofx.runner.core.matrix_utils import estimate_matrix_count

        strategy = runner.model.strategy
        if not strategy or not strategy.matrix:
            return 1
        return estimate_matrix_count(
            strategy.matrix,
            include=strategy.include,
            exclude=strategy.exclude,
        )
