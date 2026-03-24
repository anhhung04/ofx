"""Base runner class for workflow, job, and step execution"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from ofx.runner.core.durable import get_checkpoint, write_checkpoint
from ofx.runner.core.models import RunContext, RunnerStatus, RunResult
from ofx.runner.core.registry_keys import RunnerRegistryKeys
from ofx.runner.registry import RegistryAdapter, cleanup_registry
from ofx.runner.services.template_service import TemplateService
from ofx.runner.templates import TemplateResolver
from ofx.settings import settings

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


class BaseRunner[TModel: BaseModel]:
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
    )

    def __init__(
        self,
        model: TModel,
        ctx: RunContext,
        parent: BaseRunner | None = None,
        registry: RegistryAdapter | None = None,
        logger: logging.Logger | None = None,
        template_service: TemplateService | None = None,
    ):
        assert model is not None, "Model cannot be None"
        self.run_id = str(uuid.uuid4())
        self.name = f"[RUNNER][{self.run_id}]"
        self.model = model
        self.ctx = ctx
        self.parent = parent

        self._state_machine = RunnerStateMachine()
        self._error: str | None = None
        # Lazy import RegistryFactory to avoid import overhead
        if registry is None:
            from ofx.runner.registry.factory import RegistryFactory

            self._registry = RegistryFactory.create("memory")
        else:
            self._registry = registry
        # Logger injection – default to app branding logger if not provided
        self._logger = (
            logger if logger is not None else logging.getLogger(settings.app_branding)
        )
        # Template service injection – default to a new TemplateService if not provided
        from ofx.runner.services.template_service import TemplateService

        self._template_service = (
            template_service if template_service is not None else TemplateService()
        )
        self._runners: dict[str, BaseRunner] = {}  # child runners
        self._started_at: float | None = None
        self._finished_at: float | None = None
        self._started_at_utc: str | None = None
        self._finished_at_utc: str | None = None
        self._log_level = self._logger.getEffectiveLevel()
        self._durable_outputs: dict[str, Any] | None = None

    async def run(self) -> RunResult:
        """Execute the runner's lifecycle: pre_run -> do_run -> post_run"""
        self._mark_start()
        self._emit_event("runner_start")
        if await self._restore_from_checkpoint():
            self._emit_event("runner_resume")
            return await self.get_result()
        await self._write_checkpoint("running")
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
            await self._pre_run()
            self._state_machine.transition(RunnerStatus.RUNNING)
            await self._do_run()
            self._state_machine.transition(RunnerStatus.FINISHED)
            await self._post_run()
            # cleanup_registry handled in finally block
            self._state_machine.transition(RunnerStatus.COMPLETED)
        except Exception as e:
            self._error = str(e)
            if self._state_machine.current_state not in [
                RunnerStatus.FAILED,
                RunnerStatus.CANCELED,
            ]:
                self._state_machine.transition(RunnerStatus.FAILED)
        finally:
            self._mark_finish()
            self._emit_event("runner_finish", {"status": self.status.value, "error": self._error})
            initial_checkpoint_status = self._checkpoint_status()
            try:
                await self._write_checkpoint(initial_checkpoint_status)
            except Exception as checkpoint_err:
                self._log_warning(f"checkpoint write failed: {checkpoint_err}")

            final_status = self._checkpoint_status()
            if final_status != initial_checkpoint_status:
                try:
                    await self._write_checkpoint(final_status)
                except Exception:
                    self._log_warning("final checkpoint update skipped due to error")

            try:
                await cleanup_registry(self._registry)
            except Exception as cleanup_err:
                self._log_warning(f"registry cleanup failed: {cleanup_err}")
        return await self.get_result()

    def _event_sink_path(self) -> Path | None:
        path = getattr(self.ctx, "event_sink_path", None)
        if path:
            return path
        return None

    def _emit_event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Emit structured runner lifecycle event as NDJSON (best effort)."""
        sink = self._event_sink_path()
        if sink is None:
            return
        try:
            sink.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": datetime.now(UTC).isoformat(),
                "event_type": event_type,
                "runner_type": self.__class__.__name__,
                "run_id": self.run_id,
                "status": self.status.value,
                "name": getattr(self.model, "name", ""),
                "job_id": getattr(self.model, "jid", None),
                "step_index": getattr(self.model, "step_index", None),
                "parent_run_id": self.parent.run_id if self.parent else None,
            }
            if payload:
                entry.update(payload)
            with open(sink, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as exc:
            self._log_warning(f"event emit failed: {exc}")

    async def _write_checkpoint(self, status: str) -> None:
        config = self._durable_config()
        if not config or not self.ctx.output_path:
            return

        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "checkpoint_id": self._checkpoint_id(),
            "status": status,
            "runner_type": self.__class__.__name__,
            "model_type": type(self.model).__name__,
            "name": getattr(self.model, "name", None),
            "parent_run_id": self.parent.run_id if self.parent else None,
            "started_at": self._started_at_utc,
            "finished_at": self._finished_at_utc,
            "duration_ms": self.duration_ms(),
            "error": self._error,
            "job_id": getattr(self.model, "jid", None),
            "step_index": getattr(self.model, "step_index", None),
        }

        if status != "running":
            try:
                result = await self.get_result()
                payload["outputs"] = result.outputs
            except Exception as e:
                self._log_warning(f"Failed to retrieve outputs for checkpoint: {e}")
                payload["outputs"] = {}

        await write_checkpoint(
            self.ctx.output_path,
            config,
            self._checkpoint_id(),
            payload,
        )

    async def _restore_from_checkpoint(self) -> bool:
        config = self._durable_config()
        if not config or not config.resume or not self.ctx.output_path:
            return False

        checkpoint = await get_checkpoint(
            self.ctx.output_path,
            config,
            self._checkpoint_id(),
        )
        if not checkpoint or checkpoint.get("status") != "completed":
            return False

        self._error = checkpoint.get("error")
        self._durable_outputs = checkpoint.get("outputs", {})
        self._started_at_utc = checkpoint.get("started_at")
        self._finished_at_utc = checkpoint.get("finished_at")
        self._state_machine.set_state(RunnerStatus.COMPLETED)
        if self._durable_outputs is not None:
            await self.reg_set(RunnerRegistryKeys.OUTPUTS, self._durable_outputs)
        return True

    def _durable_config(self):
        """Return the durable config, cached after first lookup.
        This avoids repeated attribute traversal for each checkpoint operation.
        """
        if (
            hasattr(self, "_cached_durable_config")
            and self._cached_durable_config is not None
        ):
            return self._cached_durable_config
        if self.ctx.durable and self.ctx.durable.enabled:
            self._cached_durable_config = self.ctx.durable
            return self._cached_durable_config
        if self.parent and self.parent.ctx.durable and self.parent.ctx.durable.enabled:
            self._cached_durable_config = self.parent.ctx.durable
            return self._cached_durable_config
        self._cached_durable_config = None
        return None

    def _checkpoint_id(self) -> str:
        parent_id = self.parent._checkpoint_id() if self.parent else "workflow"
        if hasattr(self.model, "jid") and hasattr(self.model, "step_index"):
            local_id = f"job:{self.model.jid}:{self.model.step_index}"
        elif hasattr(self.model, "jid"):
            local_id = f"job:{self.model.jid}"
        elif hasattr(self.model, "name"):
            local_id = f"{self.__class__.__name__}:{self.model.name}"
        else:
            local_id = f"{self.__class__.__name__}:{self.run_id}"
        return f"{parent_id}/{local_id}"

    def _checkpoint_status(self) -> str:
        status = self.status
        if status == RunnerStatus.FINISHED:
            status = RunnerStatus.COMPLETED
        return status.value

    async def _do_run(self) -> None:
        """Execute the runner's main logic - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses should implement _do_run method.")

    async def _pre_run(self) -> None:
        """Pre-run - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses should implement _pre_run method.")

    async def _post_run(self) -> None:
        """Post-run - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses should implement _post_run method.")

    @property
    def _template_resolver(self) -> TemplateResolver:
        """Lazily import and cache the TemplateResolver.
        This avoids importing heavy Jinja2 machinery at startup.
        """
        if not hasattr(self, "__lazy_template_resolver"):
            from ofx.runner.templates.resolver import TemplateResolver

            self.__lazy_template_resolver = TemplateResolver()
        return self.__lazy_template_resolver

    async def _resolve_template(self, value: Any) -> Any:
        """Resolve Jinja2 templates in values using the injected TemplateService.
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
                "env": context_vars.get("envs", {}),
            }
        )
        return await self._template_service.resolve(
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
        self._logger.debug(self._produce_log(message))

    def _log_info(self, message: Any) -> None:
        self._logger.info(self._produce_log(message))

    def _log_warning(self, message: Any) -> None:
        self._logger.warning(self._produce_log(message))

    def _log_error(self, message: Any) -> None:
        self._logger.error(self._produce_log(message))

    def _mark_start(self) -> None:
        self._started_at = time.perf_counter()
        self._started_at_utc = datetime.now(UTC).isoformat()

    def _mark_finish(self) -> None:
        if self._finished_at is None:
            self._finished_at = time.perf_counter()
            self._finished_at_utc = datetime.now(UTC).isoformat()

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
