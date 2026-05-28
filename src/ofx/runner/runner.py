"""Lifecycle-focused runner primitive for OFX execution."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from pydantic import BaseModel

from ofx.runner.context import RunContext, RunnerContextBuilder, RunnerStatus, RunResult
from ofx.runner.executors.base import Executor
from ofx.runner.lifecycle import LifecycleManager, RunnerStateMachine
from ofx.runner.logging import StructuredLogger, get_logger
from ofx.runner.registry_adapter import RegistryAdapter
from ofx.runner.services.event_emitter import EventEmitter
from ofx.runner.templates import TemplateResolver


class Runner[TModel: BaseModel]:
    """Lean runner that owns lifecycle state and delegates execution."""

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
        "_cached_key_prefix",
        "_cached_durable_config",
        "_template_resolver_instance",
        "_lifecycle",
        "_executor",
        "_event_emitter",
        "_structured_logger",
    )

    def __init__(
        self,
        model: TModel,
        ctx: RunContext,
        parent: Runner[Any] | None = None,
        registry: RegistryAdapter | None = None,
        *,
        lifecycle: LifecycleManager | None = None,
        executor: Executor | None = None,
        event_emitter: EventEmitter | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if model is None:
            raise ValueError("Model cannot be None")
        self.run_id = str(uuid.uuid4())
        self.name = f"[RUNNER][{self.run_id}]"
        self.model = model
        self.ctx = ctx
        self.parent = parent
        self._state_machine = RunnerStateMachine()
        self._error: str | None = None
        if registry is None:
            from ofx.runner.registry import RegistryFactory

            self._registry = RegistryFactory.create("memory")
        else:
            self._registry = registry
        self._runners: dict[str, Runner[Any]] = {}
        self._started_at: float | None = None
        self._finished_at: float | None = None
        self._started_at_utc: str | None = None
        self._finished_at_utc: str | None = None
        self._log_level = (logger or get_logger()).getEffectiveLevel()
        self._durable_outputs: dict[str, Any] | None = None
        self._cached_key_prefix: str | None = None
        self._cached_durable_config: Any = None
        self._template_resolver_instance: TemplateResolver | None = None
        self._executor = executor
        self._event_emitter = event_emitter or EventEmitter(self)
        self._structured_logger = StructuredLogger(self, logger=logger)
        self._lifecycle = lifecycle or LifecycleManager(self)

    async def run(self) -> RunResult:
        return await self._lifecycle.execute()

    def update_context(self, **update: Any) -> RunContext:
        self.ctx = RunnerContextBuilder(self.ctx).with_update(update)
        return self.ctx

    def update_env(self, env: dict[str, Any]) -> RunContext:
        self.ctx = RunnerContextBuilder(self.ctx).with_env(env)
        return self.ctx

    def update_inputs(self, inputs: dict[str, Any]) -> RunContext:
        self.ctx = RunnerContextBuilder(self.ctx).with_inputs(inputs)
        return self.ctx

    def update_secrets(self, secrets: dict[str, Any]) -> RunContext:
        self.ctx = RunnerContextBuilder(self.ctx).with_secrets(secrets)
        return self.ctx

    def update_vars(self, vars_update: dict[str, Any]) -> RunContext:
        self.ctx = RunnerContextBuilder(self.ctx).with_vars(vars_update)
        return self.ctx

    def update_env_and_vars(
        self,
        env: dict[str, Any],
        vars_update: dict[str, Any],
    ) -> RunContext:
        self.ctx = RunnerContextBuilder(self.ctx).with_env_and_vars(env, vars_update)
        return self.ctx

    async def _on_failure_cleanup(self) -> None:
        if self._executor is not None:
            await self._executor.on_failure(self)

    def add_event_listener(self, event_type: str, callback: Any) -> None:
        self._lifecycle.add_event_listener(event_type, callback)

    def _emit_event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self._lifecycle.emit_event(event_type, payload)

    async def _write_checkpoint(self, status: str) -> None:
        await self._lifecycle.write_checkpoint(status)

    async def _restore_from_checkpoint(self) -> bool:
        return await self._lifecycle.restore_from_checkpoint()

    def _durable_config(self):
        return self._lifecycle.durable_config()

    def _checkpoint_id(self) -> str:
        return self._lifecycle.checkpoint_id()

    def _checkpoint_status(self) -> str:
        return self._lifecycle.checkpoint_status()

    async def _auto_commit_push(self) -> None:
        await self._lifecycle.auto_commit_push()

    async def _do_run(self) -> None:
        if self._executor is None:
            raise NotImplementedError("Runner requires an executor")
        await self._executor.do_run(self)

    async def _pre_run(self) -> None:
        if self._executor is not None:
            await self._executor.pre_run(self)

    async def _post_run(self) -> None:
        if self._executor is not None:
            await self._executor.post_run(self)

    @property
    def _template_resolver(self) -> TemplateResolver:
        if self._template_resolver_instance is None:
            self._template_resolver_instance = TemplateResolver()
        return self._template_resolver_instance

    def _build_template_context(self) -> dict[str, Any]:
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
        self,
        value: Any,
        context_vars: dict[str, Any] | None = None,
    ) -> Any:
        return await self._template_resolver.resolve(
            value,
            context_vars or self._build_template_context(),
        )

    def _evaluate_run_if(
        self,
        expr: Any,
        context: dict[str, Any] | None = None,
    ) -> bool:
        if expr is None:
            return True
        if isinstance(expr, bool):
            return expr
        if isinstance(expr, (int, float)):
            return bool(expr)
        eval_context = context or {}
        return bool(eval(str(expr), {}, eval_context))

    async def _resolve_job_outputs(self) -> dict[str, Any]:
        outputs = getattr(self.model, "outputs", None)
        if not outputs:
            return {}
        resolved: dict[str, Any] = {}
        for key, value in outputs.items():
            try:
                resolved[key] = await self._resolve_template(value)
            except Exception as exc:
                self._log_warning(f"Failed to resolve output '{key}': {exc}")
                resolved[key] = ""
        return resolved

    async def _resolve_template_fields(self, fields: list[str]) -> bool:
        if not fields:
            return False
        import asyncio

        tasks = []
        target_fields = []
        for field in fields:
            if hasattr(self.model, field):
                tasks.append(asyncio.create_task(self._resolve_template(getattr(self.model, field))))
                target_fields.append(field)
        if not tasks:
            return False
        results = await asyncio.gather(*tasks)
        for field, resolved_value in zip(target_fields, results, strict=True):
            setattr(self.model, field, resolved_value)
        return True

    def _child_context(self, update: dict[str, Any] | None = None, *, deep: bool = True) -> RunContext:
        update = update or {}
        return self.ctx.model_copy(update=update, deep=deep)

    def _produce_log(self, message: Any) -> str:
        return self._structured_logger._message(message)

    def _log_debug(self, message: Any) -> None:
        self._structured_logger.debug(message)

    def _log_info(self, message: Any) -> None:
        self._structured_logger.info(message)

    def _log_warning(self, message: Any) -> None:
        self._structured_logger.warning(message)

    def _log_error(self, message: Any) -> None:
        self._structured_logger.error(message)

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
        return self._state_machine.current_state

    @property
    def is_finished(self) -> bool:
        return self._state_machine.is_terminal

    @property
    def is_success(self) -> bool:
        return self.status == RunnerStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        return self.status == RunnerStatus.FAILED

    @property
    def registry(self) -> RegistryAdapter | None:
        return self._registry

    @property
    def runners(self) -> dict[str, Runner[Any]]:
        return self._runners

    async def get_result(self) -> RunResult:
        status = RunnerStatus.COMPLETED if self.status == RunnerStatus.FINISHED else self.status
        outputs = await self.reg_get("outputs") or {}
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
        await self._require_registry().set(self.get_key(key), value)

    async def reg_get(self, key: str) -> dict[str, Any] | None:
        return await self._require_registry().get(self.get_key(key))

    async def reg_update(self, key: str, updates: dict[str, Any]) -> None:
        await self._require_registry().update(self.get_key(key), updates)

    async def reg_set_many(self, items: dict[str, dict[str, Any]]) -> None:
        for key, value in items.items():
            await self.reg_set(key, value)

    def _require_registry(self) -> RegistryAdapter:
        if self._registry is None:
            raise RuntimeError("Runner registry is not configured")
        return self._registry

    def _namespace(self) -> str:
        return f"{self.__class__.__name__}:{self.name}"

    def get_key(self, key: str) -> str:
        prefix = self._cached_key_prefix
        if prefix is None:
            prefix = self._build_key_prefix()
            self._cached_key_prefix = prefix
        return f"{prefix}{key}" if prefix else key

    def _build_key_prefix(self) -> str:
        parts: list[str] = []
        runner: Runner[Any] | None = self
        while runner is not None:
            parts.append(runner._namespace())
            runner = runner.parent
        parts.reverse()
        return ":".join(parts) + ":"

    @property
    def log_level(self) -> int:
        return self._log_level

    @log_level.setter
    def log_level(self, level: int) -> None:
        self._log_level = level


BaseRunner = Runner

__all__ = ["BaseRunner", "Runner"]
