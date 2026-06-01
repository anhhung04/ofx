"""Pipe runner for declarative ETL between workflow steps."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ofx.models.pipe import PipeConfig
from ofx.runner.context import RunContext
from ofx.runner.executors.pipe import (
    PipeExecutor,
    _coerce_to_list,
    _execute_pipeline,
    _format_items,
    _item_namespace,
    _safe_eval,
)
from ofx.runner.runner import Runner


class PipeExecution(BaseModel):
    """Execution model wrapping a [`PipeConfig`](src/ofx/models/pipe.py)."""

    pipe: PipeConfig
    resolved_input: list = Field(default_factory=list)


class PipeRunner(Runner[PipeExecution]):
    """Execute a declarative ETL pipeline and store results as step outputs."""

    def __init__(
        self,
        model: PipeExecution,
        ctx: RunContext,
        parent: Runner | None = None,
        executor: PipeExecutor | None = None,
    ):
        super().__init__(model, ctx, parent, None, executor=executor or PipeExecutor())
        self._temp_file: Path | None = None


__all__ = [
    "PipeExecution",
    "PipeRunner",
    "_coerce_to_list",
    "_execute_pipeline",
    "_format_items",
    "_item_namespace",
    "_safe_eval",
]
