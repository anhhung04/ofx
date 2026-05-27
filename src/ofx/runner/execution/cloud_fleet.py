"""Cloud fleet runner - expands fleet targets across VPS instances."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.core import BaseRunner, RunContext, RunResult
from ofx.runner.executors.fleet import FleetExecutor
from ofx.runner.logging import get_logger

logger = get_logger()


class CloudFleetRunner(BaseRunner[Job]):
    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
        executor: FleetExecutor | None = None,
    ):
        fleet_executor = executor or FleetExecutor()
        self._fleet_executor: FleetExecutor = fleet_executor
        super().__init__(job, ctx, parent, executor=fleet_executor)
        self.name = f"CloudFleet{self.name}"
        self._fleet_combos: list[dict[str, Any]] = []
        self._chunk_files: list[Path] = []

    async def run(self) -> RunResult:
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

    def _expand_fleet(self) -> list[dict[str, Any]]:
        return self._fleet_executor.expand_fleet(self)

    async def _run_single_fleet_job(self, idx: int, combo: dict[str, Any]) -> RunResult:
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
                parent=self.parent,  # type: ignore[arg-type]
            )
        else:
            from ofx.runner.execution.cloud_job import CloudJobRunner

            runner = CloudJobRunner(
                job_copy,
                job_ctx,
                parent=self.parent,  # type: ignore[arg-type]
            )

        runner._is_fleet_child = True
        self._runners[new_jid] = runner
        return await runner.run()

    async def _report_surviving_instances(self) -> None:
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
                f"  {jid}: {inst.name} [{inst.instance_id}] @ {inst.ip} (provider={provider})"
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
                except Exception as exc:
                    self._log_warning(f"Failed to destroy {inst_name}: {exc}")
        else:
            self._log_warning(
                "Fleet instances left running - destroy manually when done."
            )

    def _cleanup_chunk_files(self) -> None:
        self._fleet_executor.cleanup_chunk_files(self)
