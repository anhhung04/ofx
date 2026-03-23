"""Cloud matrix job runner — provisions one VPS and runs all matrix combos on it.

Extends ``CloudJobRunner`` to inherit VPS provisioning. Overrides
``_do_run`` to iterate over matrix combinations on the same remote host.
"""

from __future__ import annotations

import asyncio
import itertools
from typing import Any

from ofx.models.cloud import CloudConfig
from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.core import BaseRunner, RunContext
from ofx.runner.execution.cloud_job import CloudJobRunner
from ofx.runner.logging import get_logger

logger = get_logger()


class CloudMatrixJobRunner(CloudJobRunner):
    """Provisions a single VPS, then runs all matrix combinations on it.

    Inherits provisioning, output download, and teardown from
    ``CloudJobRunner``.  Overrides ``_do_run`` to loop over the expanded
    matrix combinations, running every job step for each combination on
    the same remote host.

    YAML example::

        jobs:
          exploit:
            cloud:
              provider: aws
              region: us-east-1
            strategy:
              matrix:
                tool: [sqlmap, nuclei]
                target: [app1.com, app2.com]
            steps:
              - run: ${{ matrix.tool }} -u ${{ matrix.target }}
    """

    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
        cloud_config: CloudConfig | None = None,
    ):
        super().__init__(job, ctx, parent, cloud_config)
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

    # ------------------------------------------------------------------
    # Do-run: expand matrix → run each combo on the same VPS
    # ------------------------------------------------------------------

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

        strategy = self.model.strategy
        max_parallel = getattr(strategy, "max_parallel", None) or len(
            self._matrix_combinations
        )
        fail_fast = getattr(strategy, "fail_fast", True)
        semaphore = asyncio.Semaphore(max_parallel)
        failed_event = asyncio.Event()

        async def run_combo(idx: int, combo: dict[str, Any]):
            if fail_fast and failed_event.is_set():
                return None
            async with semaphore:
                if fail_fast and failed_event.is_set():
                    return None
                try:
                    result = await self._run_steps(combo, suffix=f"_{idx}")
                    return result
                except Exception as exc:
                    failed_event.set()
                    raise exc

        tasks = [
            asyncio.create_task(run_combo(idx, combo))
            for idx, combo in enumerate(self._matrix_combinations)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors = [
            f"Matrix {i}: {r}"
            for i, r in enumerate(results)
            if r is not None and isinstance(r, Exception)
        ]
        if errors:
            raise RuntimeError("; ".join(errors))

    def _generate_matrix_combinations(self) -> list[dict[str, Any]]:
        """Generate all matrix combinations with include/exclude rules"""
        strategy = self.model.strategy
        if not strategy or not strategy.matrix:
            return []

        matrix_keys = list(strategy.matrix.keys())
        matrix_values = [strategy.matrix[key] for key in matrix_keys]

        base_combinations = [
            dict(zip(matrix_keys, combination, strict=True))
            for combination in itertools.product(*matrix_values)
        ]

        def _matches_matrix_filter(
            combo: dict[str, Any], filters: list[dict[str, Any]]
        ) -> bool:
            """Check if a combination matches any filter"""
            for filter_dict in filters:
                if all(combo.get(key) == value for key, value in filter_dict.items()):
                    return True
            return False

        if strategy.exclude:
            base_combinations = [
                combo
                for combo in base_combinations
                if not _matches_matrix_filter(combo, strategy.exclude)
            ]

        if strategy.include:
            for include_combo in strategy.include:
                if include_combo not in base_combinations:
                    base_combinations.append(include_combo)

        return base_combinations
