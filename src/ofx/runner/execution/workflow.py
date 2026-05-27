"""Workflow runner for parallel job execution and workflow orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ofx.models.workflow import Workflow
from ofx.runner.core import BaseRunner, RegistryAdapter, RunContext
from ofx.runner.executors.workflow import WorkflowExecutor
from ofx.runner.logging import get_logger

if TYPE_CHECKING:
    from ofx.profiles.models import OFXProfile
    from ofx.profiles.time_window import TimeWindowGuard

logger = get_logger()


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
        self._workflow_executor: WorkflowExecutor = workflow_executor
        self._is_reused = self.parent is not None
        if not self._is_reused:
            self.name = f"[RUN-{self.run_id}]:{self.name}"
        self._profile: OFXProfile | None = None
        self._time_guard: TimeWindowGuard | None = None

    async def _process_inputs(
        self,
        req_inputs: dict,
        input_blueprint: dict,
    ) -> dict[str, Any]:
        return await self._workflow_executor.process_inputs(
            self,
            req_inputs,
            input_blueprint,
        )

    def _check_input_type(self, value: Any, input_type: str) -> bool:
        return self._workflow_executor.check_input_type(value, input_type)

    def _expand_list_inputs_to_matrix(self) -> None:
        self._workflow_executor.expand_list_inputs_to_matrix(self)

    @staticmethod
    def _job_references_input(job, key: str) -> bool:
        return WorkflowExecutor.job_references_input(job, key)

    async def _apply_profile(self) -> None:
        await self._workflow_executor.apply_profile(self)

    def _apply_cli_time_window(self) -> None:
        self._workflow_executor.apply_cli_time_window(self)

    async def _install_tools(self) -> None:
        await self._workflow_executor.install_tools(self)

    async def _plan_jobs(self) -> None:
        await self._workflow_executor.plan_jobs(self)

    async def _run_workflow(self) -> None:
        await self._workflow_executor.run_workflow(self)

    async def _store_summaries(self) -> None:
        await self._workflow_executor.store_summaries(self)

    async def _auto_export_findings(self, existing_outputs: dict) -> None:
        await self._workflow_executor.auto_export_findings(self, existing_outputs)

    def _produce_log(self, message: Any) -> str:
        return self._workflow_executor.produce_log(self, message)

    @property
    def runners(self) -> dict[str, BaseRunner[Any]]:
        return {
            key: runner
            for key, runner in self._runners.items()
            if isinstance(runner, BaseRunner)
        }
