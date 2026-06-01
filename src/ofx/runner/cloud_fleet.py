"""Cloud fleet runner - expands fleet targets across VPS instances."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.context import RunContext
from ofx.runner.executors.fleet import FleetExecutor
from ofx.runner.runner import Runner


class CloudFleetRunner(Runner[Job]):
    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: Runner[Workflow],
        executor: FleetExecutor | None = None,
    ):
        super().__init__(job, ctx, parent, executor=executor or FleetExecutor())
        self.name = f"CloudFleet{self.name}"
        self._fleet_combos: list[dict[str, Any]] = []
        self._chunk_files: list[Path] = []

    def _produce_log(self, message: Any) -> str:
        formatted = f"'{self.model.jid}' [cloud-fleet] › {message}"
        if self.parent is not None:
            return self.parent._produce_log(formatted)
        return formatted
