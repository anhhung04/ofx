"""Executors for cloud fleet runners."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from ofx.runner.context import RunnerStatus, RunResult
from ofx.runner.executors import Executor
from ofx.utils.file_cleanup import remove_files_and_parent_dir
from ofx.runner.executors.parallel import (
    parallel_run_settings,
    run_parallel_runner_items,
)


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

        max_parallel, fail_fast = parallel_run_settings(
            runner.model.strategy,
            item_count=len(runner._fleet_combos),
        )
        errors = await run_parallel_runner_items(
            runner._fleet_combos,
            max_parallel=max_parallel,
            fail_fast=fail_fast,
            run_item=lambda idx, combo: self.run_single_fleet_job(runner, idx, combo),
            describe_item=lambda idx, _combo: f"Fleet {idx}",
        )

        if errors:
            await self.report_surviving_instances(runner)
            raise RuntimeError("; ".join(errors))

    async def post_run(self, runner) -> None:
        remove_files_and_parent_dir(
            runner._chunk_files,
            on_error=lambda message: runner._logger.debug(message),
            file_label="chunk file",
            dir_label="chunk dir",
            clear=runner._chunk_files,
        )

    on_failure = post_run

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

    async def run_single_fleet_job(
        self,
        runner,
        idx: int,
        combo: dict[str, Any],
    ) -> RunResult:
        fleet_vars = {k: v for k, v in combo.items() if k.startswith("fleet_")}

        from ofx.runner.job import attach_indexed_job_runner, build_indexed_job_context

        job_ctx = build_indexed_job_context(
            runner,
            vars_update={"fleet": fleet_vars} if fleet_vars else None,
        )

        if runner.model.strategy and runner.model.strategy.matrix:
            from ofx.runner.cloud_matrix import CloudMatrixJobRunner

            runner_cls = CloudMatrixJobRunner
        else:
            from ofx.runner.cloud_job import CloudJobRunner

            runner_cls = CloudJobRunner

        _job_copy, child_runner = attach_indexed_job_runner(
            runner,
            ctx=job_ctx,
            index=idx,
            values=combo,
            runner_cls=runner_cls,
        )
        return await child_runner.run()

    async def report_surviving_instances(self, runner) -> None:
        from ofx.runner.cloud_job import CloudJobRunner
        from ofx.runner.executors.cloud import CloudExecutor

        surviving_runners: list[CloudJobRunner] = []
        surviving_lines: list[str] = []
        for jid, child_runner in runner._runners.items():
            if not isinstance(child_runner, CloudJobRunner):
                continue
            state = CloudExecutor._cloud_instance_state(child_runner)
            if not state.has_reportable_instance:
                continue
            surviving_runners.append(child_runner)
            surviving_lines.append(
                f"  {jid}: {state.instance_name} [{state.instance_id}] "
                f"@ {state.instance_ip} (provider={state.provider_name})"
            )

        if not surviving_runners:
            return

        instance_list = "\n".join(surviving_lines)
        runner._log_warning(
            f"Cloud instances from failed fleet may still be running:\n{instance_list}"
        )

        should_destroy = False
        if sys.stdin.isatty():
            try:
                answer = await asyncio.to_thread(
                    input,
                    "\n⚠  Cloud instance still running: "
                    f"{len(surviving_runners)} fleet instance(s):\n{instance_list}\n"
                    "   Destroy this instance? [y/N]: ",
                )
                should_destroy = answer.strip().lower() in ("y", "yes")
            except (EOFError, KeyboardInterrupt):
                should_destroy = False

        if should_destroy:
            for child_runner in surviving_runners:
                inst_name = child_runner._instance.name if child_runner._instance else "unknown"
                try:
                    await child_runner._cloud_executor.destroy_instance(child_runner)
                except Exception as exc:
                    runner._log_warning(f"Failed to destroy {inst_name}: {exc}")
        else:
            runner._log_warning(
                "Fleet instances left running - destroy manually when done."
            )
