"""Cloud matrix job runner - provisions one VPS and runs all matrix combos on it."""

from __future__ import annotations

from typing import Any

from ofx.models.cloud import CloudConfig
from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.cloud_job import CloudJobRunner, cloud_job_log_prefix
from ofx.runner.context import RunContext, RunnerStatus, RunResult
from ofx.runner.executors.matrix import MatrixExecutor
from ofx.runner.logging import bubble_tagged_log
from ofx.runner.runner import BaseRunner


class CloudMatrixExecutor(MatrixExecutor):
    """Run each matrix combination as remote steps on one cloud instance."""

    async def run_single_job(
        self,
        runner,
        matrix_idx: int,
        matrix_values: dict[str, Any],
    ) -> RunResult:
        await runner.dispatch_remote_steps(matrix_values, suffix=f"_{matrix_idx}")
        return RunResult(
            name=runner.name,
            run_id=runner.run_id,
            status=RunnerStatus.COMPLETED,
        )


class CloudMatrixJobRunner(CloudJobRunner):
    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
        cloud_config: CloudConfig | None = None,
        executor: MatrixExecutor | None = None,
    ):
        matrix_executor = executor or CloudMatrixExecutor()
        self._matrix_executor: MatrixExecutor = matrix_executor
        super().__init__(
            job,
            ctx,
            parent,
            cloud_config,
        )
        self._matrix_combinations: list[dict[str, Any]] = []

    def _produce_log(self, message: Any) -> str:
        fleet_vars = self.ctx.vars.get("fleet", {}) if hasattr(self, "ctx") else {}
        return bubble_tagged_log(
            self.parent,
            message,
            prefix=cloud_job_log_prefix(
                self.model.jid,
                fleet_name=fleet_vars.get("fleet_name", "cloud-fleet") if fleet_vars else "",
                quote_job_id=True,
            ),
            tags=("cloud-matrix",),
        )

    async def _do_run(self) -> None:
        self._log_info(
            f"Starting cloud matrix job '{self.model.name or self.model.jid}' "
            f"on {self._instance.ip if self._instance else 'unknown'}"
        )

        await self._upload_fleet_input()

        self._matrix_combinations = self._matrix_executor.generate_matrix_combinations(self)
        self._log_debug(
            f"Expanded {len(self._matrix_combinations)} matrix combination(s)"
        )

        if not self._matrix_combinations:
            await self.dispatch_remote_steps(None)
            return

        await self._matrix_executor.do_run(self)
