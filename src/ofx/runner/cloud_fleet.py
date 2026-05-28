"""Cloud fleet runner - expands fleet targets across VPS instances."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.cloud_job import cloud_job_log_prefix
from ofx.runner.context import RunContext
from ofx.runner.executors.fleet import FleetExecutor
from ofx.runner.logging import bubble_tagged_log
from ofx.runner.runner import BaseRunner


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

    def _produce_log(self, message: Any) -> str:
        return bubble_tagged_log(
            self.parent,
            message,
            prefix=cloud_job_log_prefix(self.model.jid, quote_job_id=True),
            tags=("cloud-fleet",),
        )
