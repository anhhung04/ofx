"""Cloud fleet runner — expands fleet targets across VPS instances.

Splits targets across N VPS instances using :func:`expand_fleet_to_matrix`.
Each VPS receives a chunk file and runs the job via ``CloudJobRunner`` (no
matrix) or ``CloudMatrixJobRunner`` (has matrix).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.core import (
    BaseRunner,
    RunContext,
    RunnerStatus,
    RunResult,
)
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class CloudFleetRunner(BaseRunner[Job]):
    """Spawns one VPS per fleet chunk, delegating to the appropriate runner.

    When the job also has a ``strategy.matrix``, each VPS runs all matrix
    combinations locally via ``CloudMatrixJobRunner``.  Otherwise each VPS
    runs the job steps directly via ``CloudJobRunner``.

    YAML example::

        jobs:
          scan:
            cloud: do-nyc
            strategy:
              fleet:
                count: 5
                input: targets.txt
                distribution: chunk
              matrix:
                tool: [nmap, masscan]
            steps:
              - run: {{ matrix.tool }} -iL $REMOTE_FLEET_INPUT_FILE
    """

    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
    ):
        super().__init__(job, ctx, parent)
        self.name = f"CloudFleet{self.name}"
        self._fleet_combos: list[dict[str, Any]] = []
        self._chunk_files: list[Path] = []

    async def run(self) -> RunResult:
        """Override to guarantee chunk-file cleanup regardless of outcome."""
        try:
            return await super().run()
        finally:
            self._cleanup_chunk_files()

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        msg = f"'{self.model.jid}' [cloud-fleet] › {message_str}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    # ------------------------------------------------------------------
    # Pre-run: expand fleet
    # ------------------------------------------------------------------

    async def _pre_run(self) -> None:
        await self._resolve_template_fields(["strategy"])
        self._fleet_combos = self._expand_fleet()
        self._log_debug(
            f"Expanded {len(self._fleet_combos)} fleet chunk(s) "
            f"for '{self.model.name or self.model.jid}'"
        )

    def _expand_fleet(self) -> list[dict[str, Any]]:
        """Expand fleet strategy into per-instance combinations with chunk files."""
        strategy = self.model.strategy
        if not strategy or not strategy.fleet:
            return [{}]

        from ofx.cloud.fleet_distributor import expand_fleet_to_matrix

        fleet = strategy.fleet
        combos, self._chunk_files = expand_fleet_to_matrix(
            fleet_config={
                "count": fleet.count,
                "input": fleet.input,
                "distribution": fleet.distribution,
                "exclude": fleet.exclude,
                "min_prefix": fleet.min_prefix,
                "name": self.model.name or self.model.jid,
            },
            expand_cidrs=fleet.expand_cidrs,
        )
        return combos or []

    # ------------------------------------------------------------------
    # Do-run: spawn one runner per fleet chunk
    # ------------------------------------------------------------------

    async def _do_run(self) -> None:
        if not self._fleet_combos:
            raise RuntimeError(
                f"Fleet job '{self.model.jid}' has no targets to distribute. "
                "Check the fleet input configuration."
            )

        strategy = self.model.strategy
        max_parallel = strategy.max_parallel if strategy else len(self._fleet_combos)
        fail_fast = strategy.fail_fast if strategy else True
        semaphore = asyncio.Semaphore(max_parallel)
        failed_event = asyncio.Event()

        async def run_instance(idx: int, combo: dict[str, Any]):
            if fail_fast and failed_event.is_set():
                return None
            async with semaphore:
                if fail_fast and failed_event.is_set():
                    return None
                result = await self._run_single_fleet_job(idx, combo)
                if isinstance(result, RunResult) and result.status != RunnerStatus.COMPLETED:
                    failed_event.set()
                return result

        tasks = [
            asyncio.create_task(run_instance(idx, combo))
            for idx, combo in enumerate(self._fleet_combos)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors = []
        for i, result in enumerate(results):
            if result is None:
                continue  # skipped due to fail_fast
            if isinstance(result, Exception):
                errors.append(f"Fleet {i}: {result}")
            elif (
                isinstance(result, RunResult)
                and result.status != RunnerStatus.COMPLETED
            ):
                errors.append(f"Fleet {i}: {result.error or 'Failed'}")

        if errors:
            await self._report_surviving_instances()
            raise RuntimeError("; ".join(errors))

    async def _run_single_fleet_job(self, idx: int, combo: dict[str, Any]) -> RunResult:
        """Provision a VPS and run the job for one fleet chunk."""
        job_ctx = self._child_context()

        if self.model.strategy:
            job_ctx.vars["strategy"] = self.model.strategy.model_dump()

        fleet_vars = {k: v for k, v in combo.items() if k.startswith("fleet_")}
        if fleet_vars:
            job_ctx.vars["fleet"] = fleet_vars

        new_jid = f"{self.model.jid}_{idx}"
        job_copy = self.model.model_copy(
            deep=True,
            update={
                "name": f"[{self.model.name or self.model.jid}]{{{idx}}}",
                "jid": new_jid,
                "matrix_values": combo,
                "matrix_index": idx,
            },
        )

        has_matrix = self.model.strategy and self.model.strategy.matrix
        if has_matrix:
            from ofx.runner.execution.cloud_matrix import CloudMatrixJobRunner

            runner = CloudMatrixJobRunner(
                job_copy,
                job_ctx,
                parent=self.parent,  # type: ignore
            )
        else:
            from ofx.runner.execution.cloud_job import CloudJobRunner

            runner = CloudJobRunner(
                job_copy,
                job_ctx,
                parent=self.parent,  # type: ignore
            )

        runner._is_fleet_child = True
        self._runners[new_jid] = runner
        return await runner.run()

    # ------------------------------------------------------------------
    # Surviving instance cleanup
    # ------------------------------------------------------------------

    async def _report_surviving_instances(self) -> None:
        """Prompt the user to destroy surviving cloud instances after failure."""
        from ofx.runner.execution.cloud_job import (
            CloudJobRunner,
            _prompt_destroy_instance,
        )

        surviving_runners: list[CloudJobRunner] = []
        surviving_lines: list[str] = []
        for jid, runner in self._runners.items():
            if not isinstance(runner, CloudJobRunner):
                continue
            inst = runner._instance
            if not inst or not inst.ip:
                continue
            provider = inst.provider or "unknown"
            if provider == "static":
                continue
            surviving_runners.append(runner)
            surviving_lines.append(
                f"  {jid}: {inst.name} [{inst.instance_id}] "
                f"@ {inst.ip} (provider={provider})"
            )

        if not surviving_runners:
            return

        instance_list = "\n".join(surviving_lines)
        self._log_warning(
            f"Cloud instances from failed fleet may still be running:\n{instance_list}"
        )

        should_destroy = await _prompt_destroy_instance(
            f"{len(surviving_runners)} fleet instance(s):\n{instance_list}"
        )

        if should_destroy:
            for runner in surviving_runners:
                inst_name = runner._instance.name if runner._instance else "unknown"
                try:
                    await runner._destroy_instance()
                except Exception as e:
                    self._log_warning(f"Failed to destroy {inst_name}: {e}")
        else:
            self._log_warning(
                "Fleet instances left running — destroy manually when done."
            )

    # ------------------------------------------------------------------
    # Post-run: cleanup fleet chunk files
    # ------------------------------------------------------------------

    async def _post_run(self) -> None:
        self._cleanup_chunk_files()

    def _cleanup_chunk_files(self) -> None:
        """Remove temporary fleet chunk files and their parent directory."""
        if not self._chunk_files:
            return
        parent_dir = None
        for f in self._chunk_files:
            try:
                if f.exists():
                    if parent_dir is None:
                        parent_dir = f.parent
                    f.unlink()
            except Exception as e:
                logger.debug("Failed to remove chunk file %s: %s", f, e)
        if parent_dir:
            try:
                parent_dir.rmdir()
            except OSError as e:
                logger.debug("Failed to remove chunk dir %s: %s", parent_dir, e)
        self._chunk_files.clear()
