"""Workflow runner for parallel job execution and workflow orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ofx.models.workflow import Workflow
from ofx.runner.context import RunContext
from ofx.runner.executors.workflow import WorkflowExecutor
from ofx.runner.logging import bubble_context_log
from ofx.runner.registry_adapter import RegistryAdapter
from ofx.runner.runner import BaseRunner

if TYPE_CHECKING:
    from ofx.profiles.models import OFXProfile
    from ofx.profiles.time_window import TimeWindowGuard

class WorkflowRunner(BaseRunner[Workflow]):
    def __init__(
        self,
        workflow: Workflow,
        ctx: RunContext,
        parent: BaseRunner | None = None,
        registry: RegistryAdapter | None = None,
        executor: WorkflowExecutor | None = None,
    ):
        workflow_executor = executor or WorkflowExecutor()
        super().__init__(
            workflow,
            ctx,
            parent,
            registry,
            executor=workflow_executor,
        )
        self._is_reused = self.parent is not None
        if not self._is_reused:
            self.name = f"[RUN-{self.run_id}]:{self.name}"
        self._profile: OFXProfile | None = None
        self._time_guard: TimeWindowGuard | None = None

    def _produce_log(self, message: Any) -> str:
        return bubble_context_log(self.parent, message, model_name=self.model.name)

    @property
    def runners(self) -> dict[str, BaseRunner[Any]]:
        return {
            key: runner
            for key, runner in self._runners.items()
            if isinstance(runner, BaseRunner)
        }
