"""Base runner class for workflow, job, and step execution"""

import asyncio
import logging
import uuid
from typing import Any, Optional, TypeVar

from pydantic import BaseModel

from ofx.runner.core.models import RunContext, RunnerStatus, RunResult
from ofx.runner.templates import TemplateResolver
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

TModel = TypeVar("TModel", bound=BaseModel)


class BaseRunner[TModel]:
    """Abstract base class for all runners (workflow, job, step, command)

    Type Parameters:
        TModel: The model type this runner executes (Workflow, Job, Step, etc.)
    """

    def __init__(
        self, model: TModel, ctx: RunContext, parent: Optional["BaseRunner"] = None
    ):
        name = str(model) if model is not None else "unknown"
        self.model = model
        self.parent = parent
        self.ctx_vars = ctx
        self.run_id = str(uuid.uuid4())

        self._status = RunnerStatus.IDLE
        self._error: str | None = None
        self._result = RunResult(status=self.status, run_id=self.run_id, name=name)
        self._template_resolver = TemplateResolver()

    async def run(self) -> RunResult:
        """Execute the runner's lifecycle: pre_run -> do_run -> post_run"""
        try:
            self._status = RunnerStatus.IDLE
            self.ctx_vars.vars.update({"self": self.model})
            await self._pre_run()
            self._status = RunnerStatus.RUNNING
            await self._do_run()
            self._status = RunnerStatus.FINISHED
            await self._post_run()
            self._status = RunnerStatus.COMPLETED
        except Exception as e:
            self._error = f"Error ({type(e).__name__}): {e}"
            self._status = RunnerStatus.FAILED

        return self.get_result()

    async def _do_run(self) -> None:
        """Execute the runner's main logic - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses should implement _do_run method.")

    async def _pre_run(self) -> None:
        """Pre-run hook - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses should implement _pre_run method.")

    async def _post_run(self) -> None:
        """Post-run hook - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses should implement _post_run method.")

    async def _resolve_template(self, value: Any) -> Any:
        """Resolve Jinja2 templates in values using TemplateResolver

        Args:
            value: Value to resolve (can be str, dict, list, primitives)

        Returns:
            Resolved value with templates expanded
        """
        # Prepare context variables
        context_vars = self.ctx_vars.model_dump(exclude={"vars"})
        if self.ctx_vars.vars:
            context_vars.update(self.ctx_vars.vars)
        return await self._template_resolver.resolve(
            value,
            context_vars,
            self.run_id,
        )

    async def _resolve_template_fields(self, fields: list[str]) -> bool:
        """Resolve templates in specific model fields in parallel

        Args:
            fields: List of field names to resolve
        """
        if not self.model or not fields:
            return False

        tasks = []
        target_fields = []
        for field in fields:
            if hasattr(self.model, field):
                tasks.append(
                    asyncio.create_task(
                        self._resolve_template(getattr(self.model, field))
                    )
                )
                target_fields.append(field)
        if tasks:
            results = await asyncio.gather(*tasks)
            for field, resolved_value in zip(target_fields, results, strict=True):
                setattr(self.model, field, resolved_value)
            return True
        return False

    def _produce_log(self, message: Any) -> str:
        """Produce a log message - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses should implement _produce_log method.")

    @property
    def status(self) -> RunnerStatus:
        """Get the current status"""
        return self._status

    @property
    def is_finished(self) -> bool:
        """Check if execution is finished"""
        return self._status in {RunnerStatus.COMPLETED, RunnerStatus.FAILED}

    @property
    def is_success(self) -> bool:
        """Check if execution succeeded"""
        return self._status == RunnerStatus.COMPLETED and self._error is None

    def get_result(self) -> RunResult:
        """Get the execution result"""
        self._result.status = self.status
        self._result.error = self._error
        return self._result

    def get_job_status(self, job_id: str) -> RunnerStatus | None:
        """Get job status from registry (WorkflowRunner override)"""
        return None

    def get_job_from_registry(self, job_id: str) -> dict[str, Any] | None:
        """Get job from registry (WorkflowRunner override)"""
        return None
