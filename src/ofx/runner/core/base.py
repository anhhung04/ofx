"""Base runner class for workflow, job, and step execution"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

from ofx.runner.core.models import RunContext, RunnerStatus, RunResult
from ofx.runner.core.registry_keys import RunnerRegistryKeys
from ofx.runner.registry import RegistryAdapter, cleanup_registry
from ofx.runner.registry.factory import RegistryFactory
from ofx.runner.templates import TemplateResolver
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

TModel = TypeVar("TModel", bound=BaseModel)


class RunnerStateMachine:
    """Finite State Machine for managing runner execution states"""

    def __init__(self):
        self._current_state = RunnerStatus.IDLE
        self._transitions = {
            RunnerStatus.IDLE: [
                RunnerStatus.RUNNING,
                RunnerStatus.CANCELED,
                RunnerStatus.FAILED,
            ],
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


class BaseRunner(Generic[TModel]):
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
        self.run_id = str(uuid.uuid4())
        self.name = f"[RUNNER][{self.run_id}]"
        self.model = model
        self.ctx = ctx
        self.parent = parent

        self._state_machine = RunnerStateMachine()
        self._error: str | None = None
        self._template_resolver = TemplateResolver()
        self._registry = registry or RegistryFactory.create_memory()
        self._runners: dict[str, BaseRunner] = {}  # child runners
        self._started_at: float | None = None
        self._finished_at: float | None = None
        self._started_at_utc: str | None = None
        self._finished_at_utc: str | None = None
        self._log_level = logging.getLogger().getEffectiveLevel()

    async def run(self) -> RunResult:
        """Execute the runner's lifecycle: pre_run -> do_run -> post_run"""
        self._mark_start()
        try:
            await self.reg_set(
                "metadata",
                {
                    "run_id": self.run_id,
                    "name": self.name,
                    "type": str(type(self.model)),
                },
            )
            await self.reg_set(
                "context", self.ctx.model_dump(exclude={"secrets", "envs"})
            )

            # Execute lifecycle
            await self._on_start()
            await self._pre_run()
            self._state_machine.transition(RunnerStatus.RUNNING)
            await self._do_run()
            self._state_machine.transition(RunnerStatus.FINISHED)
            await self._post_run()
            await self._on_success()
            await cleanup_registry(self._registry)
            self._state_machine.transition(RunnerStatus.COMPLETED)
        except Exception as e:
            self._error = f"Error ({type(e).__name__}): {e}"
            await self._on_error(e)
            if self._state_machine.current_state not in [
                RunnerStatus.FAILED,
                RunnerStatus.CANCELED,
            ]:
                self._state_machine.transition(RunnerStatus.FAILED)
        finally:
            self._mark_finish()
            await self._on_finish()
            await cleanup_registry(self._registry)
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
        context_vars = self.ctx.vars.copy()
        context_vars.update(self.ctx.model_dump(exclude={"vars"}))
        context_vars.update(
            {
                "self": self.model,
                "registry": self._registry,
                "runner": self,
                "ctx": self.ctx,
            }
        )
        return await self._template_resolver.resolve(
            value,
            context_vars,
        )

    def _evaluate_run_if(
        self, expr: Any, context: dict[str, Any] | None = None
    ) -> bool:
        """Evaluate run_if using provided context helpers."""
        if expr is None:
            return True
        if isinstance(expr, bool):
            return expr
        if isinstance(expr, (int, float)):
            return bool(expr)
        eval_context = context or {}
        return bool(eval(str(expr), {}, eval_context))

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

    def _child_context(
        self, update: dict[str, Any] | None = None, *, deep: bool = True
    ) -> RunContext:
        """Create a child RunContext with optional updates."""
        update = update or {}
        return self.ctx.model_copy(update=update, deep=deep)

    def _produce_log(self, message: Any) -> str:
        """Produce a log message - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses should implement _produce_log method.")

    def _log_debug(self, message: Any) -> None:
        logger.debug(self._produce_log(message))

    def _log_info(self, message: Any) -> None:
        logger.info(self._produce_log(message))

    def _log_warning(self, message: Any) -> None:
        logger.warning(self._produce_log(message))

    def _log_error(self, message: Any) -> None:
        logger.error(self._produce_log(message))

    def _mark_start(self) -> None:
        self._started_at = time.perf_counter()
        self._started_at_utc = datetime.now(timezone.utc).isoformat()

    def _mark_finish(self) -> None:
        if self._finished_at is None:
            self._finished_at = time.perf_counter()
            self._finished_at_utc = datetime.now(timezone.utc).isoformat()

    @property
    def started_at(self) -> str | None:
        return self._started_at_utc

    @property
    def finished_at(self) -> str | None:
        return self._finished_at_utc

    def duration_ms(self) -> int | None:
        if self._started_at is None:
            return None
        end = self._finished_at or time.perf_counter()
        return int((end - self._started_at) * 1000)

    async def _on_start(self) -> None:
        """Lifecycle hook called before pre_run."""
        self._log_debug("runner start")

    async def _on_success(self) -> None:
        """Lifecycle hook called after post_run when completed successfully."""
        self._log_debug("runner success")

    async def _on_error(self, error: Exception) -> None:
        """Lifecycle hook called when an error is raised."""
        if self.log_level <= logging.ERROR:
            self._log_error(f"runner error: {error}")

    async def _on_finish(self) -> None:
        """Lifecycle hook called at the end of run regardless of outcome."""
        self._log_debug("runner finish")

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
        return self.status == RunnerStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """Check if execution failed"""
        return self.status == RunnerStatus.FAILED

    @property
    def registry(self) -> RegistryAdapter:
        """Get the registry adapter"""
        return self._registry

    async def get_result(self) -> RunResult:
        """Get the execution result"""
        status = (
            RunnerStatus.COMPLETED
            if self.status == RunnerStatus.FINISHED
            else self.status
        )
        return RunResult(
            name=self.name,
            run_id=self.run_id,
            status=status,
            error=self._error,
            outputs=await self.reg_get(RunnerRegistryKeys.OUTPUTS) or {},
        )

    async def reg_set(self, key: str, value: dict[str, Any]) -> None:
        """Store namespaced data in the registry."""
        await self._registry.set(self.get_key(key), value)

    async def reg_get(self, key: str) -> dict[str, Any] | None:
        """Retrieve namespaced data from the registry."""
        return await self._registry.get(self.get_key(key))

    async def reg_update(self, key: str, updates: dict[str, Any]) -> None:
        """Update namespaced data in the registry."""
        await self._registry.update(self.get_key(key), updates)

    async def reg_set_global(self, key: str, value: dict[str, Any]) -> None:
        """Store data with a raw, non-namespaced key."""
        await self._registry.set(key, value)

    async def reg_get_global(self, key: str) -> dict[str, Any] | None:
        """Retrieve data with a raw, non-namespaced key."""
        return await self._registry.get(key)

    async def reg_update_global(self, key: str, updates: dict[str, Any]) -> None:
        """Update data with a raw, non-namespaced key."""
        await self._registry.update(key, updates)

    async def reg_set_raw(self, key: str, value: dict[str, Any]) -> None:
        """Store data using an already-prefixed key."""
        await self._registry.set(key, value)

    async def reg_update_raw(self, key: str, updates: dict[str, Any]) -> None:
        """Update data using an already-prefixed key."""
        await self._registry.update(key, updates)

    def _namespace(self) -> str:
        """Namespace prefix for registry keys."""
        return f"{self.__class__.__name__}:{self.name}"

    def get_key(self, key: str) -> str:
        """Generate a namespaced key for the runner"""
        key = f"{self._namespace()}:{key}"
        if self.parent:
            return self.parent.get_key(key)
        return key

    @property
    def log_level(self) -> int:
        """Get the current log level"""
        return self._log_level

    @log_level.setter
    def log_level(self, level: int) -> None:
        """Set the log level"""
        self._log_level = level
