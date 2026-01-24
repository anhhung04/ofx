"""Base runner class for workflow, job, and step execution"""

import asyncio
import logging
import uuid
from typing import Any, Optional, TypeVar

from pydantic import BaseModel

from ofx.runner.core.models import RunContext, RunnerStatus, RunResult
from ofx.runner.core.registries import RegistryAdapter, cleanup_registry
from ofx.runner.core.registries.factory import RegistryFactory
from ofx.runner.templates import TemplateResolver
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

TModel = TypeVar("TModel", bound=BaseModel)


class RunnerStateMachine:
    """Finite State Machine for managing runner execution states"""

    def __init__(self):
        self._current_state = RunnerStatus.IDLE
        self._transitions = {
            RunnerStatus.IDLE: [RunnerStatus.RUNNING, RunnerStatus.CANCELED, RunnerStatus.FAILED],
            RunnerStatus.RUNNING: [RunnerStatus.FINISHED, RunnerStatus.FAILED],
            RunnerStatus.FINISHED: [RunnerStatus.COMPLETED, RunnerStatus.FAILED],
            RunnerStatus.FAILED: [],
            RunnerStatus.COMPLETED: [],
            RunnerStatus.CANCELED: [],
        }

    def can_transition(self, to_state: RunnerStatus) -> bool:
        """Check if transition to the given state is allowed"""
        return to_state in self._transitions[self._current_state]

    def transition(self, to_state: RunnerStatus) -> None:
        """Transition to the given state if allowed"""
        if not self.can_transition(to_state):
            raise ValueError(
                f"Invalid state transition from {self._current_state} to {to_state}"
            )
        self._current_state = to_state

    @property
    def current_state(self) -> RunnerStatus:
        """Get the current state"""
        return self._current_state

    @property
    def is_terminal(self) -> bool:
        """Check if current state is terminal (no further transitions allowed)"""
        return not self._transitions[self._current_state]

    def set_state(self, state: RunnerStatus) -> None:
        """Set the state directly (for internal use, bypassing transition checks)"""
        self._current_state = state


class BaseRunner[TModel]:
    """Abstract base class for all runners (workflow, job, step, command)
    Type Parameters:
        TModel: The model type this runner executes (Workflow, Job, Step, etc.)
    """

    def __init__(
        self,
        model: TModel,
        ctx: RunContext,
        parent: Optional["BaseRunner"] = None,
        registry: RegistryAdapter | None = None,
    ):
        assert model is not None, "Model cannot be None"
        self.name = f"{str(model)}[RUNNER]"
        self.run_id = str(uuid.uuid4())
        self.model = model
        self.ctx = ctx
        self.parent = parent

        self._state_machine = RunnerStateMachine()
        self._error: str | None = None
        self._template_resolver = TemplateResolver()
        self._registry = registry or RegistryFactory.create_memory()

    async def run(self) -> RunResult:
        """Execute the runner's lifecycle: pre_run -> do_run -> post_run"""
        try:
            await self._registry.set(
                self.get_key("metadata"),
                {
                    "run_id": self.run_id,
                    "name": self.name,
                    "type": str(type(self.model)),
                },
            )
            await self._registry.set(self.get_key("context"), self.ctx.model_dump())

            # Execute lifecycle
            await self._pre_run()
            self._state_machine.transition(RunnerStatus.RUNNING)
            await self._do_run()
            self._state_machine.transition(RunnerStatus.FINISHED)
            await self._post_run()
            await cleanup_registry(self._registry)
            self._state_machine.transition(RunnerStatus.COMPLETED)
        except Exception as e:
            self._error = f"Error ({type(e).__name__}): {e}"
            if self._state_machine.current_state not in [
                RunnerStatus.FAILED,
                RunnerStatus.CANCELED,
            ]:
                self._state_machine.transition(RunnerStatus.FAILED)

        return await self.get_result()

    async def _do_run(self) -> None:
        """Execute the runner's main logic - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses should implement _do_run method.")

    async def _pre_run(self) -> None:
        """Pre-run - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses should implement _pre_run method.")

    async def _post_run(self) -> None:
        """Post-run - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses should implement _post_run method.")

    async def _resolve_template(self, value: Any) -> Any:
        """Resolve Jinja2 templates in values using TemplateResolver
        Args:
            value: Value to resolve (can be str, dict, list, primitives)
        Returns:
            Resolved value with templates expanded
        """
        context_vars = self.ctx.vars
        context_vars.update(self.ctx.model_dump(exclude={"vars"}))
        context_vars.update({"self": self.model})
        return await self._template_resolver.resolve(
            value,
            context_vars,
        )

    async def _resolve_template_fields(self, fields: list[str]) -> bool:
        """Resolve templates in specific model fields in parallel
        Args:
            fields: List of field names to resolve
        """
        if not fields:
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
        return self._state_machine.current_state

    @property
    def is_finished(self) -> bool:
        """Check if execution is finished"""
        return self._state_machine.is_terminal

    @property
    def is_success(self) -> bool:
        """Check if execution succeeded"""
        return self.is_finished and self._error is None

    @property
    def is_failed(self) -> bool:
        """Check if execution failed"""
        return self.is_finished and self._error is not None

    @property
    def registry(self) -> RegistryAdapter:
        """Get the registry adapter"""
        return self._registry

    async def get_result(self) -> RunResult:
        """Get the execution result"""
        return RunResult(
            name=self.name,
            run_id=self.run_id,
            status=self.status,
            error=self._error,
            outputs=await self._registry.get("outputs") or {},
        )

    def get_key(self, key: str) -> str:
        """Generate a namespaced key for the runner"""
        key = f"{self.name}:{key}"
        if self.parent:
            return self.parent.get_key(key)
        return key
