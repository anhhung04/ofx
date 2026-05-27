"""Executors for cloud fleet runners."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ofx.runner.core.models import RunnerStatus, RunResult
from ofx.runner.executors import Executor


class FleetExecutor(Executor):
    """Fleet-specific execution logic extracted from cloud fleet runners."""

    async def pre_run(self, runner) -> None:
        await runner._resolve_template_fields(["strategy"])
        runner._fleet_combos = self.expand_fleet(runner)
        runner._log_debug(
            f"Expanded {len(runner._fleet_combos)} fleet chunk(s) "
            f"for '{runner.model.name or runner.model.jid}'"
        )

    async def do_run(self, runner) -> None:
        if not runner._fleet_combos:
            raise RuntimeError(
                f"Fleet job '{runner.model.jid}' has no targets to distribute. "
                "Check the fleet input configuration."
            )

        strategy = runner.model.strategy
        max_parallel = strategy.max_parallel if strategy else len(runner._fleet_combos)
        fail_fast = strategy.fail_fast if strategy else True
        semaphore = asyncio.Semaphore(max_parallel)
        failed_event = asyncio.Event()

        async def run_instance(idx: int, combo: dict[str, Any]):
            if fail_fast and failed_event.is_set():
                return None
            async with semaphore:
                if fail_fast and failed_event.is_set():
                    return None
                result = await runner._run_single_fleet_job(idx, combo)
                if (
                    isinstance(result, RunResult)
                    and result.status != RunnerStatus.COMPLETED
                ):
                    failed_event.set()
                return result

        tasks = [
            asyncio.create_task(run_instance(idx, combo))
            for idx, combo in enumerate(runner._fleet_combos)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors = []
        for i, result in enumerate(results):
            if result is None:
                continue
            if isinstance(result, Exception):
                errors.append(f"Fleet {i}: {result}")
            elif (
                isinstance(result, RunResult)
                and result.status != RunnerStatus.COMPLETED
            ):
                errors.append(f"Fleet {i}: {result.error or 'Failed'}")

        if errors:
            await runner._report_surviving_instances()
            raise RuntimeError("; ".join(errors))

    async def post_run(self, runner) -> None:
        runner._cleanup_chunk_files()

    def expand_fleet(self, runner) -> list[dict[str, Any]]:
        """Expand fleet strategy into per-instance combinations with chunk files."""
        strategy = runner.model.strategy
        if not strategy or not strategy.fleet:
            return [{}]

        from ofx.cloud.fleet_distributor import expand_fleet_to_matrix

        fleet = strategy.fleet
        combos, runner._chunk_files = expand_fleet_to_matrix(
            fleet_config={
                "count": fleet.count,
                "input": fleet.input,
                "distribution": fleet.distribution,
                "exclude": fleet.exclude,
                "min_prefix": fleet.min_prefix,
                "name": runner.model.name or runner.model.jid,
            },
            expand_cidrs=fleet.expand_cidrs,
        )
        return combos or []

    def cleanup_chunk_files(self, runner) -> None:
        """Remove temporary fleet chunk files and their parent directory."""
        if not runner._chunk_files:
            return
        parent_dir = None
        for chunk_file in runner._chunk_files:
            try:
                if chunk_file.exists():
                    if parent_dir is None:
                        parent_dir = chunk_file.parent
                    chunk_file.unlink()
            except Exception as exc:
                runner._logger.debug(
                    "Failed to remove chunk file %s: %s", chunk_file, exc
                )
        if parent_dir:
            try:
                parent_dir.rmdir()
            except OSError as exc:
                runner._logger.debug(
                    "Failed to remove chunk dir %s: %s", parent_dir, exc
                )
        runner._chunk_files.clear()
