"""Executor for cloud matrix job runners.

Expands matrix combinations across remote steps on a single cloud VPS instance.
"""

from __future__ import annotations

from typing import Any

from ofx.runner.context import RunnerStatus, RunResult
from ofx.runner.executors.matrix import MatrixExecutor

class CloudMatrixExecutor(MatrixExecutor):
    """Run each matrix combination as remote steps on one cloud instance."""

    async def run_single_job(
        self,
        runner,
        matrix_idx: int,
        matrix_values: dict[str, Any],
    ) -> RunResult:
        await runner._cloud_executor.dispatch_remote_steps(
            runner,
            matrix_values,
            suffix=f"_{matrix_idx}",
        )
        return RunResult(
            name=runner.name,
            run_id=runner.run_id,
            status=RunnerStatus.COMPLETED,
        )

__all__ = ["CloudMatrixExecutor"]
