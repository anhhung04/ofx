"""Lifecycle-focused runner primitive for OFX execution."""

from __future__ import annotations

import ast
import asyncio
import logging
import os
import uuid
from typing import Any

from pydantic import BaseModel

from ofx.runner.context import (
    RunContext,
    RunnerStatus,
    RunResult,
    context_with_env,
    context_with_secrets,
    context_with_update,
    context_with_vars,
    normalize_runner_status,
)
from ofx.runner.executors.base import Executor
from ofx.runner.lifecycle import LifecycleManager, RunnerStateMachine
from ofx.runner.logging import StructuredLogger, get_logger
from ofx.runner.registry_adapter import RegistryAdapter
from ofx.runner.services.event_emitter import EventEmitter
from ofx.runner.templates import TemplateResolver


class _DeferredLogger:
    """Resolve the shared OFX logger on first actual use.

    ``Runner.__init__`` used to call :func:`get_logger` eagerly, which
    reconfigures global logging (``reload_logging_config``) as a side effect
    of merely constructing a runner.  This proxy defers that resolution
    until the first log emission (or log-level read), so constructing runners
    never mutates global logging state while every actual log call keeps
    behaving identically for existing callers.
    """

    __slots__ = ("_logger",)

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger

    def __getattr__(self, name: str) -> Any:
        logger = self._logger
        if logger is None:
            logger = get_logger()
            self._logger = logger
        return getattr(logger, name)


# Restricted builtins for ``run_if`` expression evaluation.  Mirrors the
# sandbox from ``ofx.runner.executors.pipe`` ("_safe_eval"): arbitrary code
# (imports, open, eval, dunder attribute access) must never run from a
# workflow YAML ``if:``/``run_if:`` string.
_RUN_IF_SAFE_BUILTINS: dict[str, Any] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "len": len,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "sorted": sorted,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "any": any,
    "all": all,
    "round": round,
    "isinstance": isinstance,
    "True": True,
    "False": False,
    "None": None,
}


def _safe_run_if_eval(expr: str, namespace: dict[str, Any]) -> Any:
    """Evaluate *expr* with a restricted set of builtins.

    Duplicated from ``ofx.runner.executors.pipe._safe_eval`` (rather than
    imported) to keep the runner core free of executor-internal coupling.
    The AST walk rejects ``__import__``/``eval``/``open``/``compile`` and any
    dunder attribute access, and evaluation runs against only the restricted
    builtins above, so a workflow ``run_if`` string cannot execute arbitrary
    code.
    """
    code = compile(expr, "<run-if-expr>", "eval")
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in (
            "__import__",
            "exec",
            "eval",
            "open",
            "compile",
            "globals",
            "locals",
            "getattr",
            "setattr",
            "delattr",
            "__builtins__",
        ):
            raise ValueError(f"Forbidden name in run_if expression: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError(
                f"Forbidden dunder attribute access in run_if expression: {node.attr}"
            )
    safe_ns: dict[str, Any] = {"__builtins__": {}}
    safe_ns.update(_RUN_IF_SAFE_BUILTINS)
    safe_ns.update(namespace)
    return eval(code, safe_ns)


class Runner[TModel: BaseModel]:
    """Lean runner that owns lifecycle state and delegates execution.

    Note on ``__slots__``: the base class deliberately does **not** declare
    ``__slots__``.  Earlier this class declared a fixed tuple of slot names,
    but every subclass (and the executors that dynamically attach state such
    as ``_time_guard``, ``_run_dir``, ``_chunk_files``,
    ``_matrix_combinations``, ``_cloud_config``, ``_profile``, etc.) relied
    on a real ``__dict__``.  The slot tuple was decorative/misleading — it
    silently left ``__dict__`` in place while claiming to restrict
    attributes.  Removing it keeps every attribute assignment working
    unchanged (subclass instances still carry ``__dict__``), which is the
    safe option given the breadth of dynamic attributes set across
    ``runner/``.
    """

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
        # Avoid calling get_logger() here — it reconfigures global logging
        # (reload_logging_config) as a side effect.  When an explicit logger
        # is provided its effective level is still captured immediately
        # (callers that set log_level rely on that); otherwise resolution is
        # deferred to first use via the deferred logger / log_level getter so
        # plain runner construction never mutates global logging state.
        self._log_level: int | None = (
            logger.getEffectiveLevel() if logger is not None else None
        )
        self._cached_key_prefix: str | None = None
        self._cached_durable_config: Any = None
        self._template_resolver_instance: TemplateResolver | None = None
        self._executor = executor
        self._event_emitter = event_emitter or EventEmitter(self)
        self._structured_logger = StructuredLogger(
            self, logger=_DeferredLogger(logger)
        )
        self._lifecycle = lifecycle or LifecycleManager(
            self,
            event_emitter=self._event_emitter,
        )

    async def run(self) -> RunResult:
        # Idempotent re-run guard: calling run() on a runner that is already
        # in a terminal state returns the cached result instead of re-entering
        # the lifecycle, which would raise a misleading FSM ValueError from
        # the RUNNING/COMPLETED transition.  This keeps second-run semantics
        # stable without triggering _pre_run side effects again.
        if self._state_machine.is_terminal:
            self._log_debug(
                f"run() called on terminal runner in state "
                f"{self._state_machine.current_state.value}; "
                "returning cached result"
            )
            return await self.get_result()
        return await self._lifecycle.execute()

    def _mutate_context(self, mutator, *args, **kwargs) -> RunContext:
        self.ctx = mutator(self.ctx, *args, **kwargs)
        return self.ctx

    def update_context(self, **update: Any) -> RunContext:
        return self._mutate_context(context_with_update, update)

    def update_env(self, env: dict[str, Any]) -> RunContext:
        return self._mutate_context(context_with_env, env)

    def update_inputs(self, inputs: dict[str, Any]) -> RunContext:
        return self._mutate_context(
            context_with_update,
            {"inputs": {**self.ctx.inputs, **inputs}},
        )

    def update_secrets(self, secrets: dict[str, Any]) -> RunContext:
        return self._mutate_context(context_with_secrets, secrets)

    def update_vars(self, vars_update: dict[str, Any]) -> RunContext:
        return self._mutate_context(context_with_vars, vars_update)

    def update_env_and_vars(
        self,
        env: dict[str, Any],
        vars_update: dict[str, Any],
    ) -> RunContext:
        return self._mutate_context(
            context_with_update,
            {
                "envs": {**self.ctx.envs, **env},
                "vars": {**self.ctx.vars, **vars_update},
            },
        )

    async def _on_failure_cleanup(self) -> None:
        if self._executor is not None:
            await self._executor.on_failure(self)

    def add_event_listener(self, event_type: str, callback: Any) -> None:
        self._event_emitter.add_event_listener(event_type, callback)

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
        envs = self.ctx.envs

        class EnvLookup(dict):
            """Mapping view over run env vars with ``os.environ`` fallback.

            Supports both ``{{ env.VAR }}`` mapping access and the legacy
            ``{{ env('VAR') }}`` call style.
            """

            def __missing__(self, key: str) -> Any:
                return os.environ.get(key, "")

            def __call__(self, key: str, default: str = "") -> Any:
                return envs.get(key, os.environ.get(key, default))

        return {
            **self.ctx.vars,
            **self.ctx.model_dump(exclude={"vars"}),
            "self": self.model,
            "registry": self._registry,
            "runner": self,
            "ctx": self.ctx,
            "env": EnvLookup(envs),
            "vars": self.ctx.vars,
        }

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
        return bool(_safe_run_if_eval(str(expr), eval_context))

    async def _resolve_job_outputs(self) -> dict[str, Any]:
        """Resolve a job's declared outputs from the context (fail-soft).

        Each output template is resolved independently and, if it raises,
        the failure is logged as a warning and the output falls back to an
        empty string.  This is intentional: job outputs are derived values
        consumed downstream (summaries, findings exports) and a single
        unresolvable template expression must not abort the whole workflow.
        Contrast with [Runner._resolve_template_fields][], which is
        fail-fast for step/job *configuration* fields.
        """
        outputs = getattr(self.model, "outputs", None)
        if not isinstance(outputs, dict) or not outputs:
            return {}
        keys = list(outputs)
        results = await asyncio.gather(
            *(self._resolve_template(outputs[key]) for key in keys),
            return_exceptions=True,
        )
        resolved_outputs: dict[str, Any] = {}
        for key, result in zip(keys, results, strict=True):
            if isinstance(result, Exception):
                self._log_warning(f"Failed to resolve output '{key}': {result}")
                resolved_outputs[key] = ""
            else:
                resolved_outputs[key] = result
        return resolved_outputs

    async def _resolve_template_fields(self, fields: list[str]) -> bool:
        """Resolve template fields on the runner model (fail-fast).

        Unlike [Runner._resolve_job_outputs][], which resolves *output*
        templates and tolerates per-key failures, this resolves
        *configuration* fields (name, run_if, env, defaults, working
        directory, …).  A failure here means the runner itself cannot be
        configured correctly, so the error is allowed to propagate and
        surfaces through the lifecycle's terminal-error handling.  This
        fail-fast contract is deliberate: silently swallowing a
        mis-configured field would lead to confusing, partially-applied
        behavior rather than a clear failure.
        """
        target_fields = [field for field in fields if hasattr(self.model, field)]
        if not target_fields:
            return False
        results = await asyncio.gather(
            *(self._resolve_template(getattr(self.model, field)) for field in target_fields)
        )
        for field, resolved_value in zip(target_fields, results, strict=True):
            setattr(self.model, field, resolved_value)
        if "name" in target_fields:
            # Registry keys are namespaced with the runner's name
            # (_key_prefix caches it).  The name may be resolved from raw
            # Jinja here (e.g. "build-{{ matrix.os }}"), so drop the cached
            # prefix; the next key lookup recomputes it from the resolved
            # name instead of embedding the raw template text.
            self._cached_key_prefix = None
        return True

    def _produce_log(self, message: Any) -> str:
        return self._structured_logger.format_message(message)

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

    def register_runner(self, key: str, runner: Runner[Any]) -> None:
        """Register a child runner under *key*.

        A duplicate key means two children would silently overwrite each
        other's outputs in the shared registry (the H2 class of bug), so it
        is rejected explicitly instead of clobbering the earlier runner.
        """
        if key in self._runners:
            raise ValueError(
                f"Duplicate runner key {key!r} on {self!r}: a child runner is "
                "already registered under this name"
            )
        self._runners[key] = runner

    async def get_result(self) -> RunResult:
        outputs = await self.reg_get("outputs") or {}
        return RunResult(
            name=self.name,
            run_id=self.run_id,
            status=normalize_runner_status(self.status),
            error=self._error,
            outputs=outputs,
        )

    async def reg_set(self, key: str, value: dict[str, Any]) -> None:
        await self._registry_call("set", key, value)

    async def reg_get(self, key: str) -> dict[str, Any] | None:
        return await self._registry_call("get", key)

    async def reg_update(self, key: str, updates: dict[str, Any]) -> None:
        await self._registry_call("update", key, updates)

    async def reg_set_many(self, items: dict[str, dict[str, Any]]) -> None:
        # Fan out concurrently: registry backends serialize per-key writes
        # (asyncio.Lock / filelock), and sequential awaits multiply latency
        # when a runner persists several keys at once.
        await asyncio.gather(*(self.reg_set(key, value) for key, value in items.items()))

    async def _registry_call(self, method_name: str, key: str, *args):
        registry = self._registry
        if registry is None:
            raise RuntimeError("Runner registry is not configured")
        method = getattr(registry, method_name)
        return await method(self.get_key(key), *args)

    def _namespace(self) -> str:
        return f"{self.__class__.__name__}:{self.name}"

    def get_key(self, key: str) -> str:
        prefix = self._key_prefix()
        return f"{prefix}{key}" if prefix else key

    def _key_prefix(self) -> str:
        prefix = self._cached_key_prefix
        if prefix is None:
            parts: list[str] = []
            runner: Runner[Any] | None = self
            while runner is not None:
                parts.append(runner._namespace())
                runner = runner.parent
            parts.reverse()
            prefix = ":".join(parts) + ":"
            self._cached_key_prefix = prefix
        return prefix

    @property
    def log_level(self) -> int:
        if self._log_level is None:
            # First actual use of the runner's log level resolves the shared
            # logger on demand instead of at construction time.
            self._log_level = get_logger().getEffectiveLevel()
        return self._log_level

    @log_level.setter
    def log_level(self, level: int) -> None:
        self._log_level = level

__all__ = ["Runner"]
