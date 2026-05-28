"""Executors for cloud fleet runners."""

from __future__ import annotations

from typing import Any

from ofx.runner.context import RunnerContextBuilder, RunnerStatus, RunResult
from ofx.runner.executors import Executor
from ofx.runner.executors.parallel import run_limited_fail_fast


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
        results = await run_limited_fail_fast(
            runner._fleet_combos,
            max_parallel=max_parallel,
            fail_fast=fail_fast,
            run_item=lambda idx, combo: self.run_single_fleet_job(runner, idx, combo),
            is_failure=lambda result: isinstance(result, RunResult)
            and result.status != RunnerStatus.COMPLETED,
        )

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
            await self.report_surviving_instances(runner)
            raise RuntimeError("; ".join(errors))

    async def post_run(self, runner) -> None:
        self.cleanup_chunk_files(runner)

    async def on_failure(self, runner) -> None:
        self.cleanup_chunk_files(runner)

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
        job_ctx = runner._child_context()
        vars_update: dict[str, Any] = {}

        if runner.model.strategy:
            vars_update["strategy"] = runner.model.strategy.model_dump()

        fleet_vars = {k: v for k, v in combo.items() if k.startswith("fleet_")}
        if fleet_vars:
            vars_update["fleet"] = fleet_vars

        if vars_update:
            job_ctx = RunnerContextBuilder(job_ctx).with_vars(vars_update)

        from ofx.runner.job import clone_indexed_job

        job_copy = clone_indexed_job(
            runner.model,
            idx,
            combo,
        )

        has_matrix = runner.model.strategy and runner.model.strategy.matrix
        if has_matrix:
            from ofx.runner.cloud_matrix import CloudMatrixJobRunner

            child_runner = CloudMatrixJobRunner(
                job_copy,
                job_ctx,
                parent=runner.parent,  # type: ignore[arg-type]
            )
        else:
            from ofx.runner.cloud_job import CloudJobRunner

            child_runner = CloudJobRunner(
                job_copy,
                job_ctx,
                parent=runner.parent,  # type: ignore[arg-type]
            )

        child_runner._is_fleet_child = True
        runner._runners[job_copy.jid] = child_runner
        return await child_runner.run()

    async def report_surviving_instances(self, runner) -> None:
        from ofx.runner.cloud_job import CloudJobRunner, _prompt_destroy_instance

        surviving_runners: list[CloudJobRunner] = []
        surviving_lines: list[str] = []
        for jid, child_runner in runner._runners.items():
            if not isinstance(child_runner, CloudJobRunner):
                continue
            inst = child_runner._instance
            if not inst or not inst.ip:
                continue
            provider = inst.provider or "unknown"
            if provider == "static":
                continue
            surviving_runners.append(child_runner)
            surviving_lines.append(
                f"  {jid}: {inst.name} [{inst.instance_id}] @ {inst.ip} (provider={provider})"
            )

        if not surviving_runners:
            return

        instance_list = "\n".join(surviving_lines)
        runner._log_warning(
            f"Cloud instances from failed fleet may still be running:\n{instance_list}"
        )

        should_destroy = await _prompt_destroy_instance(
            f"{len(surviving_runners)} fleet instance(s):\n{instance_list}"
        )

        if should_destroy:
            for child_runner in surviving_runners:
                inst_name = child_runner._instance.name if child_runner._instance else "unknown"
                try:
                    await child_runner.destroy_instance()
                except Exception as exc:
                    runner._log_warning(f"Failed to destroy {inst_name}: {exc}")
        else:
            runner._log_warning(
                "Fleet instances left running - destroy manually when done."
            )

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
            except OSError as exc:
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
