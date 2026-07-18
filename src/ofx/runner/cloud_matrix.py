"""Cloud matrix job runner - provisions one VPS and runs all matrix combos on it."""

from __future__ import annotations

from typing import Any

from ofx.models.cloud import CloudConfig
from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.cloud_job import CloudJobRunner
from ofx.runner.context import RunContext
from ofx.runner.executors.cloud_matrix import CloudMatrixExecutor as _CloudMatrixExecutor
from ofx.runner.executors.matrix import MatrixExecutor
from ofx.runner.metadata import ModelContext
from ofx.runner.runner import Runner

class CloudMatrixJobRunner(CloudJobRunner):
    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: Runner[Workflow],
        cloud_config: CloudConfig | None = None,
        executor: MatrixExecutor | None = None,
    ):
        self._matrix_executor: MatrixExecutor = executor or _CloudMatrixExecutor()
        super().__init__(
            job,
            ctx,
            parent,
            cloud_config,
        )
        self._matrix_combinations: list[dict[str, Any]] = []

    def _produce_log(self, message: Any) -> str:
        fleet_name = self.ctx.vars.get("fleet", {}).get("fleet_name", "")
        workflow_name = ModelContext.from_model(getattr(self.parent, "model", None)).name or ""
        prefix = f"'{self.model.jid}'"
        if workflow_name:
            prefix = f"name={workflow_name} | {prefix}"
        if fleet_name:
            prefix = f"{prefix} [{fleet_name}]"
        formatted = f"{prefix} [cloud-matrix] › {message}"
        if self.parent is not None:
            return self.parent._produce_log(formatted)
        return formatted

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
            await self._cloud_executor.dispatch_remote_steps(self, None)
            return

        await self._matrix_executor.do_run(self)

__all__ = ["CloudMatrixJobRunner"]
