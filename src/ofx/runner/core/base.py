"""Base runner class for workflow, job, and step execution"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, TypeVar

from pydantic import BaseModel

from ofx.models.config import DurableRunConfig
from ofx.runner.core.models import RunContext, RunnerStatus, RunResult
from ofx.runner.core.registry_keys import RunnerRegistryKeys
from ofx.runner.lifecycle import LifecycleManager, RunnerStateMachine
from ofx.runner.registry import RegistryAdapter
from ofx.runner.templates import TemplateResolver
from ofx.runner.executors import Executor
from ofx.settings import settings

TModel = TypeVar("TModel", bound=BaseModel)


class BaseRunner[TModel: BaseModel]:
    _cached_durable_config: DurableRunConfig | None
    __slots__ = (
        "run_id",
        "name",
        "model",
        "ctx",
        "parent",
        "_state_machine",
        "_error",
        "_registry",
        "_runners",
        "_started_at",
        "_finished_at",
        "_started_at_utc",
        "_finished_at_utc",
        "_log_level",
        "_durable_outputs",
        "__lazy_template_resolver",
        "__lazy_registry",
        "_cached_durable_config",
        "_logger",
        "_template_service",
        "_cached_key_prefix",
        "_lifecycle",
        "_executor",
    )

    def __init__(
        self,
        model: TModel,
        ctx: RunContext,
        parent: BaseRunner | None = None,
        registry: RegistryAdapter | None = None,
        logger: logging.Logger | None = None,
        executor: Executor | None = None,
    ) -> None:
        assert model is not None, "Model cannot be None"
        self.run_id = str(uuid.uuid4())
        self.name = f"[RUNNER][{self.run_id}]"
        self.model = model
        self.ctx = ctx
        self.parent = parent

        self._state_machine = RunnerStateMachine()
        self._error: str | None = None
        if registry is None:
            from ofx.runner.registry.factory import RegistryFactory

            self._registry = RegistryFactory.create("memory")
        else:
            self._registry = registry
        self._logger = (
            logger if logger is not None else logging.getLogger(settings.app_branding)
        )
        self._runners: dict[str, BaseRunner] = {}
        self._started_at: float | None = None
        self._finished_at: float | None = None
        self._started_at_utc: str | None = None
        self._finished_at_utc: str | None = None
        self._log_level = self._logger.getEffectiveLevel()
        self._durable_outputs: dict[str, Any] | None = None
        self._cached_durable_config = None
        self._lifecycle = LifecycleManager(self)
        self._executor = executor

    async def run(self) -> RunResult:
        """Execute the runner's lifecycle: pre_run -> do_run -> post_run"""
        return await self._lifecycle.execute()

    async def _on_failure_cleanup(self) -> None:
        """Hook for subclasses to perform cleanup when execution fails.

        Called only when ``_pre_run`` succeeded but ``_do_run`` or
        ``_post_run`` raised an exception. Override this instead of
        relying on ``_post_run`` for cleanup - ``_post_run`` is only
        called on the success path.
        """
        if self._executor is not None:
            await self._executor.on_failure(self)

    def add_event_listener(self, event_type: str, callback: Any) -> None:
        self._lifecycle.add_event_listener(event_type, callback)

    def _emit_event(
        self, event_type: str, payload: dict[str, Any] | None = None
    ) -> None:
        """Emit structured runner lifecycle event as NDJSON (best effort)."""
        self._lifecycle.emit_event(event_type, payload)

    async def _write_checkpoint(self, status: str) -> None:
        await self._lifecycle.write_checkpoint(status)

    async def _restore_from_checkpoint(self) -> bool:
        return await self._lifecycle.restore_from_checkpoint()

    def _durable_config(self):
        """Return the durable config, cached after first lookup."""
        return self._lifecycle.durable_config()

    def _checkpoint_id(self) -> str:
        return self._lifecycle.checkpoint_id()

    def _checkpoint_status(self) -> str:
        return self._lifecycle.checkpoint_status()

    async def _auto_commit_push(self) -> None:
        await self._lifecycle.auto_commit_push()

    async def _do_run(self) -> None:
        """Execute the runner's main logic - must be implemented by subclasses."""
        if self._executor is not None:
            await self._executor.do_run(self)
            return
        raise NotImplementedError("Subclasses should implement _do_run method.")

    async def _pre_run(self) -> None:
        """Pre-run hook. Default is no-op; override in subclasses."""
        if self._executor is not None:
            await self._executor.pre_run(self)

    async def _post_run(self) -> None:
        """Post-run hook. Default is no-op; override in subclasses."""
        if self._executor is not None:
            await self._executor.post_run(self)

    async def _resolve_job_outputs(self) -> dict[str, Any]:
        """Resolve template expressions in ``model.outputs``.

        Used by both ``JobRunner`` and ``CloudJobRunner`` post-run to
        expand Jinja2 expressions in declared job outputs. Returns
        the resolved dict (empty if the model has no outputs).
        """
        outputs = getattr(self.model, "outputs", None)
        if not outputs:
            return {}
        resolved: dict[str, Any] = {}
        for key, value in outputs.items():
            try:
                resolved[key] = await self._resolve_template(value)
            except Exception as e:
                self._log_warning(f"Failed to resolve output '{key}': {e}")
                resolved[key] = ""
        return resolved

    @property
    def _template_resolver(self) -> TemplateResolver:
        """Lazily import and cache the TemplateResolver.
        This avoids importing heavy Jinja2 machinery at startup.
        """
        if not hasattr(self, "__lazy_template_resolver"):
            from ofx.runner.templates.resolver import TemplateResolver

            self.__lazy_template_resolver = TemplateResolver()
        return self.__lazy_template_resolver

    def _build_template_context(self) -> dict[str, Any]:
        """Build the template context for runner-scoped template resolution."""
        context_vars = self.ctx.vars.copy()
        context_vars.update(self.ctx.model_dump(exclude={"vars"}))
        envs = context_vars.get("envs", {})
        context_vars.update(
            {
                "self": self.model,
                "registry": self._registry,
                "runner": self,
                "ctx": self.ctx,
                "env": lambda key, default="": envs.get(
                    key, os.environ.get(key, default)
                ),
                "vars": self.ctx.vars,
            }
        )
        return context_vars

    async def _resolve_template(
        self, value: Any, context_vars: dict[str, Any] | None = None
    ) -> Any:
        """Resolve Jinja2 templates in values using the TemplateResolver.
        Args:
            value: Value to resolve (can be str, dict, list, primitives)
            context_vars: Optional pre-built template context
        Returns:
            Resolved value with templates expanded
        """
        return await self._template_resolver.resolve(
            value,
            context_vars or self._build_template_context(),
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
        """Produce a log message. Override in subclasses for custom prefixes."""
        msg = str(message)
        if self.parent:
            return self.parent._produce_log(msg)
        return f"[{self.__class__.__name__}] {msg}"

    def _log_debug(self, message: Any) -> None:
        self._logger.debug(self._produce_log(message))

    def _log_info(self, message: Any) -> None:
        self._logger.info(self._produce_log(message))

    def _log_warning(self, message: Any) -> None:
        self._logger.warning(self._produce_log(message))

    def _log_error(self, message: Any) -> None:
        self._logger.error(self._produce_log(message))

    def _mark_start(self) -> None:
        self._lifecycle.mark_start()

    def _mark_finish(self) -> None:
        self._lifecycle.mark_finish()

    @property
    def started_at(self) -> str | None:
        return self._started_at_utc

    @property
    def finished_at(self) -> str | None:
        return self._finished_at_utc

    def duration_ms(self) -> int | None:
        return self._lifecycle.duration_ms()

    def duration_seconds(self) -> float | None:
        return self._lifecycle.duration_seconds()

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
        """Get the registry adapter, lazily load and cache RegistryFactory."""
        if not hasattr(self, "__lazy_registry"):
            from ofx.runner.registry.factory import RegistryFactory

            self.__lazy_registry = RegistryFactory.create("memory")
        return self.__lazy_registry

    async def get_result(self) -> RunResult:
        """Get the execution result"""
        status = (
            RunnerStatus.COMPLETED
            if self.status == RunnerStatus.FINISHED
            else self.status
        )
        outputs = await self.reg_get(RunnerRegistryKeys.OUTPUTS) or {}
        if self._durable_outputs is not None and not outputs:
            outputs = self._durable_outputs
        return RunResult(
            name=self.name,
            run_id=self.run_id,
            status=status,
            error=self._error,
            outputs=outputs,
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

    async def reg_set_many(self, items: dict[str, dict[str, Any]]) -> None:
        """Store multiple namespaced key-value pairs in the registry."""
        for key, value in items.items():
            await self._registry.set(self.get_key(key), value)

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
        """Generate a namespaced key for the runner.

        The prefix is cached after first computation since the parent
        chain and namespace are immutable during a runner's lifetime.
        """
        try:
            prefix = self._cached_key_prefix
        except AttributeError:
            prefix = self._build_key_prefix()
            self._cached_key_prefix = prefix
        return f"{prefix}{key}" if prefix else key

    def _build_key_prefix(self) -> str:
        """Walk the parent chain once to build the full namespace prefix."""
        parts: list[str] = []
        runner: BaseRunner | None = self
        while runner is not None:
            parts.append(runner._namespace())
            runner = runner.parent
        parts.reverse()
        return ":".join(parts) + ":"

    @property
    def log_level(self) -> int:
        """Get the current log level"""
        return self._log_level

    @log_level.setter
    def log_level(self, level: int) -> None:
        """Set the log level"""
        self._log_level = level
