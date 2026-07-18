"""Workflow stage execution manager."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from ofx.runner.context import context_with_update
from ofx.runner.runner import Runner
from ofx.runner.runner_factory import job_runner_class
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)
_MEMORY_POLL_INTERVAL = 5

@dataclass
class ExecutionResult:
    """Aggregated results from all workflow stages."""

    failed_job_ids: list[str] = field(default_factory=list)
    failed_stage_indices: list[int] = field(default_factory=list)

class WorkflowExecutionManager:
    """Executes workflow stages and aggregates errors."""

    def __init__(self, parent_runner):
        self._parent = parent_runner
        self._max_parallel_jobs = settings.max_parallel_jobs
        self._job_semaphore = asyncio.Semaphore(self._max_parallel_jobs)
        self._mem_limit = settings.memory_limit_percent

    async def run(self, schedule: list[list[str]], staged_jobs: dict):
        result = ExecutionResult()
        for stage_index, stage in enumerate(schedule):
            time_guard = getattr(self._parent, "_time_guard", None)
            if time_guard and time_guard.should_abort:
                result.failed_job_ids.extend(
                    job_id for remaining_stage in schedule[stage_index:] for job_id in remaining_stage
                )
                result.failed_stage_indices.append(stage_index)
                self._parent._log_error("🛑 Time window expired - aborting remaining stages")
                break

            stage_runners: dict[str, Runner] = {}
            stage_size = len(stage)
            for job_id in stage:
                job = staged_jobs[job_id]
                runner = job_runner_class(job)(
                    job,
                    context_with_update(
                        self._parent.ctx,
                        {"allow_interactive": stage_size == 1},
                    ),
                    parent=self._parent,
                )
                stage_runners[job_id] = runner
                self._parent._runners[job_id] = runner

            failed_jobs = await self._run_stage(stage_index, stage_runners)
            if failed_jobs:
                result.failed_stage_indices.append(stage_index)
                result.failed_job_ids.extend(failed_jobs)
        return result

    async def _wait_for_memory(self) -> None:
        if self._mem_limit <= 0:
            return
        warned = False
        while True:
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
                    usage = (1 - available / total) * 100 if total > 0 else 0.0
            except (OSError, KeyError, ValueError, ZeroDivisionError):
                logger.debug("Memory usage check unavailable, defaulting to 0%%", exc_info=True)
                usage = 0.0
            if usage <= 0 or usage < self._mem_limit:
                return
            if not warned:
                logger.warning(
                    "Memory usage %.0f%% exceeds limit %d%% - waiting before launching next job",
                    usage,
                    self._mem_limit,
                )
                warned = True
            await asyncio.sleep(_MEMORY_POLL_INTERVAL)

    async def _run_stage(
        self,
        stage_index: int,
        stage_runners: dict[str, Runner],
    ) -> list[str]:
        self._parent._log_info(
            f"Starting stage {stage_index + 1} with {len(stage_runners)} job(s) "
            f"(concurrency limit: {self._max_parallel_jobs})"
        )
        async def _run_job(job_runner: Runner) -> None:
            async with self._job_semaphore:
                await self._wait_for_memory()
                await job_runner.run()

        task_map = {
            asyncio.create_task(_run_job(job_runner)): job_id
            for job_id, job_runner in stage_runners.items()
        }
        try:
            pending = set(task_map)
            failed_jobs: list[str] = []
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    job_id = task_map[task]
                    try:
                        task.result()
                    except (asyncio.CancelledError, KeyboardInterrupt):
                        raise
                    except Exception as exc:
                        logger.debug("Job '%s' raised: %s", job_id, exc)
                    if stage_runners[job_id].is_failed:
                        failed_jobs.append(job_id)
            return failed_jobs
        except (asyncio.CancelledError, KeyboardInterrupt):
            pending = [task for task in task_map if not task.done()]
            for task in pending:
                task.cancel()
            await asyncio.gather(*task_map, return_exceptions=True)
            raise

__all__ = ["ExecutionResult", "WorkflowExecutionManager"]
