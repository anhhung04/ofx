"""Cloud matrix job runner - provisions one VPS and runs all matrix combos on it."""

from __future__ import annotations

from typing import Any

from ofx.models.cloud import CloudConfig
from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.core import BaseRunner, RunContext
from ofx.runner.executors.job import MatrixExecutor
from ofx.runner.execution.cloud_job import CloudJobRunner
from ofx.runner.logging import get_logger

logger = get_logger()


class CloudMatrixJobRunner(CloudJobRunner):
    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
        cloud_config: CloudConfig | None = None,
        executor: MatrixExecutor | None = None,
    ):
        matrix_executor = executor or MatrixExecutor()
        self._matrix_executor: MatrixExecutor = matrix_executor
        super().__init__(
            job,
            ctx,
            parent,
            cloud_config,
            executor=matrix_executor,
        )
        self._matrix_combinations: list[dict[str, Any]] = []

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        fleet_vars = self.ctx.vars.get("fleet", {}) if hasattr(self, "ctx") else {}
        if fleet_vars:
            fleet_name = fleet_vars.get("fleet_name", "cloud-fleet")
            msg = f"'{self.model.jid}' [{fleet_name}]"
        else:
            msg = f"'{self.model.jid}'"
        msg += f" [cloud-matrix] › {message_str}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    async def _do_run(self) -> None:
        self._log_info(
            f"Starting cloud matrix job '{self.model.name or self.model.jid}' "
            f"on {self._instance.ip if self._instance else 'unknown'}"
        )

        await self._upload_fleet_input()

        self._matrix_combinations = self._generate_matrix_combinations()
        self._log_debug(
            f"Expanded {len(self._matrix_combinations)} matrix combination(s)"
        )

        if not self._matrix_combinations:
            await self._run_steps(None)
            return

        await self._matrix_executor.do_run(self)

    def _generate_matrix_combinations(self) -> list[dict[str, Any]]:
        matrix_executor = getattr(self, "_matrix_executor", None) or MatrixExecutor()
        return matrix_executor.generate_matrix_combinations(self)
