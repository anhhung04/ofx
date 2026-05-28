"""Template resolver for Jinja2-based workflow templates"""

import asyncio
import json
import logging
import threading
from collections import OrderedDict
from typing import Any, Self

from jinja2 import Environment
from pydantic import BaseModel

from ofx.runner.registry_keys import RunnerRegistryKeys

_logger = logging.getLogger("ofx.templates")
_resolver_lock = threading.Lock()


def _tojson_python(value: Any, indent: int | None = None) -> str:
    """JSON serialization that outputs Python-compatible literals.

    Emits Python's ``True``/``False``/``None`` so the output can be used
    directly in inline ``script:`` blocks.
    """
    normalized = json.loads(json.dumps(value, default=str))
    return _python_literal(normalized, indent=indent)


def _python_literal(value: Any, indent: int | None = None, level: int = 0) -> str:
    """Render JSON-compatible data as a Python literal."""
    if value is True:
        return "True"
    if value is False:
        return "False"
    if value is None:
        return "None"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return _python_sequence_literal(value, indent, level)
    if isinstance(value, dict):
        return _python_mapping_literal(value, indent, level)
    return json.dumps(str(value))


def _python_sequence_literal(
    items: list[Any], indent: int | None, level: int
) -> str:
    if not items:
        return "[]"
    if indent is None:
        rendered = (_python_literal(item) for item in items)
        return f"[{', '.join(rendered)}]"

    inner_prefix = " " * indent * (level + 1)
    outer_prefix = " " * indent * level
    rendered = [
        f"{inner_prefix}{_python_literal(item, indent, level + 1)}"
        for item in items
    ]
    return "[\n" + ",\n".join(rendered) + f"\n{outer_prefix}]"


def _python_mapping_literal(
    mapping: dict[str, Any], indent: int | None, level: int
) -> str:
    if not mapping:
        return "{}"
    if indent is None:
        rendered = (
            f"{_python_literal(key)}: {_python_literal(value)}"
            for key, value in mapping.items()
        )
        return f"{{{', '.join(rendered)}}}"

    inner_prefix = " " * indent * (level + 1)
    outer_prefix = " " * indent * level
    rendered = [
        f"{inner_prefix}{_python_literal(key)}: "
        f"{_python_literal(value, indent, level + 1)}"
        for key, value in mapping.items()
    ]
    return "{\n" + ",\n".join(rendered) + f"\n{outer_prefix}}}"


def _build_jinja_env():
    """Create a Jinja2 Environment with Python-safe ``tojson`` filter."""
    env = Environment(enable_async=True)
    env.filters["tojson"] = _tojson_python
    return env


def _ensure_filters_registered(env: Environment) -> None:
    """Lazily register ETL and type-filter helpers as Jinja2 filters.

    Called once before the first template render so ``{{ items | ports }}``
    and ``{{ items | pluck("host") | to_lines }}`` work.
    """
    if getattr(env, "_ofx_filters_registered", False):
        return
    with _resolver_lock:
        if getattr(env, "_ofx_filters_registered", False):
            return
        from ofx.runner.templates.helpers import _etl_helpers, _type_filter_helpers

        for name, fn in _type_filter_helpers().items():
            env.filters[name] = fn
        for name, fn in _etl_helpers().items():
            env.filters[name] = fn
        env._ofx_filters_registered = True  # type: ignore[attr-defined]


_jinja_env = _build_jinja_env()


class _EmptyStep:
    """Safe proxy returned for missing steps so ``| default()`` works."""

    def __getattr__(self, name: str) -> Any:
        return _EmptyStep()

    def __getitem__(self, key: Any) -> Any:
        return _EmptyStep()

    def __bool__(self) -> bool:
        return False

    def __str__(self) -> str:
        return ""

    def __iter__(self):
        return iter([])

    def __add__(self, other: Any) -> Any:
        return other

    def __radd__(self, other: Any) -> Any:
        return other


_EMPTY_STEP = _EmptyStep()


class _StepAccessor(dict):
    """Dict that supports both name-based and integer-index access for steps.

    Returns a safe empty proxy for missing keys so that Jinja2 expressions
    like ``steps["missing-step"].outputs.typed_outputs | default([], true)``
    evaluate gracefully instead of raising.
    """

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            key = str(key)
        try:
            return super().__getitem__(key)
        except KeyError:
            return _EMPTY_STEP

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            return _EMPTY_STEP


class TemplateResolver:
    """Handles template resolution with caching and optimization"""

    _instance: Self | None = None
    _template_cache: OrderedDict[str, Any]
    _support_funcs_cache: dict[str, Any] | None
    _template_cache_max_size: int
    _cache_hits: int
    _cache_misses: int

    # Maximum nesting depth for recursive template resolution.
    _MAX_RESOLVE_DEPTH = 64

    def __new__(cls):
        if cls._instance is None:
            with _resolver_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._template_cache = OrderedDict()
                    inst._support_funcs_cache = None
                    inst._template_cache_max_size = 2048
                    inst._cache_hits = 0
                    inst._cache_misses = 0
                    cls._instance = inst
        return cls._instance

    async def resolve(
        self,
        value: Any,
        context_vars: dict[str, Any],
        _memo: dict[str, Any] | None = None,
    ) -> Any:
        """Resolve Jinja2 templates in values recursively with optimized caching
        Args:
            value: Value to resolve (can be str, dict, list, primitives)
            context_vars: Context variables for template rendering
        Returns:
            Resolved value with templates expanded
        """
        memo = _memo or {}
        if value is None:
            return value

        # Guard against deeply nested structures (malicious or accidental)
        depth: int = memo.get("_resolve_depth", 0)
        if depth > self._MAX_RESOLVE_DEPTH:
            raise RecursionError(
                f"Template resolution exceeded maximum depth ({self._MAX_RESOLVE_DEPTH}). "
                f"Check for deeply nested data structures."
            )
        memo["_resolve_depth"] = depth + 1

        try:
            return await self._resolve_inner(value, context_vars, memo)
        finally:
            memo["_resolve_depth"] = depth

    async def _resolve_inner(
        self,
        value: Any,
        context_vars: dict[str, Any],
        memo: dict[str, Any],
    ) -> Any:
        """Inner resolve implementation (separated for depth tracking)."""
        if isinstance(value, dict):
            return {
                k: await self.resolve(v, context_vars, memo) for k, v in value.items()
            }
        elif isinstance(value, list):
            return [await self.resolve(v, context_vars, memo) for v in value]
        elif issubclass(type(value), BaseModel):
            return value.model_copy(
                update={k: await self.resolve(v, context_vars, memo) for k, v in value}
            )
        elif not isinstance(value, (str, int, float, bool, dict, list)):
            return value

        value_str = str(value)
        if "{{" not in value_str and "{%" not in value_str:
            return value

        # Circular reference detection
        resolve_stack: list[str] = memo.setdefault("_resolve_stack", [])
        if value_str in resolve_stack:
            chain = " → ".join(resolve_stack + [value_str])
            raise ValueError(f"Circular template reference detected: {chain}")
        resolve_stack.append(value_str)

        support_funcs = await self._build_support_functions(context_vars, memo)

        _ensure_filters_registered(_jinja_env)

        if value_str in self._template_cache:
            self._template_cache.move_to_end(value_str)
            self._cache_hits += 1
        else:
            self._cache_misses += 1
            if len(self._template_cache) >= self._template_cache_max_size:
                self._template_cache.popitem(last=False)
            self._template_cache[value_str] = _jinja_env.from_string(value_str)

        template = self._template_cache[value_str]

        template_vars = context_vars.copy()
        template_vars.update(support_funcs)

        try:
            result = await template.render_async(template_vars)
        except Exception as e:
            # Redact secret values from the error preview to avoid leaking
            preview = value_str[:120] + ("…" if len(value_str) > 120 else "")
            secrets_dict = context_vars.get("secrets")
            if isinstance(secrets_dict, dict):
                for secret_val in secrets_dict.values():
                    sv = str(secret_val)
                    if len(sv) >= 4:
                        preview = preview.replace(sv, "***")
            # List available top-level variables for debugging
            available = sorted(
                k for k in template_vars if not k.startswith("_") and k != "secrets"
            )
            raise type(e)(
                f"Template rendering failed: {e}\n"
                f"  Template: {preview}\n"
                f"  Available variables: {', '.join(available[:20])}"
            ) from e

        resolve_stack.pop()

        if isinstance(value, bool):
            return result.lower() in ("true", "yes", "1", "t", "y")
        elif isinstance(value, int):
            try:
                return int(result)
            except ValueError:
                _logger.debug(
                    "Template returned non-integer '%s' for int field, "
                    "keeping as string (template: %s)",
                    result[:50],
                    value_str[:80],
                )
                return result
        elif isinstance(value, float):
            try:
                return float(result)
            except ValueError:
                _logger.debug(
                    "Template returned non-float '%s' for float field, "
                    "keeping as string (template: %s)",
                    result[:50],
                    value_str[:80],
                )
                return result

        return result

    def get_support_functions(self) -> dict[str, Any]:
        """Get template support functions with caching"""
        if self._support_funcs_cache is None:
            from ofx.runner.templates.helpers import build_all_helpers

            self._support_funcs_cache = build_all_helpers()

        return self._support_funcs_cache.copy()

    async def _build_support_functions(
        self, context_vars: dict[str, Any], memo: dict[str, Any]
    ) -> dict[str, Any]:
        """Build support functions once per resolve call and reuse in recursion."""

        if "support_funcs" in memo:
            return memo["support_funcs"]

        support_funcs = self.get_support_functions()

        runner = context_vars.get("runner")
        if runner is not None:
            jobs_data: dict[str, Any] = memo.get("jobs_data", {})
            steps_data: dict[str, Any] = memo.get("steps_data", {})
            if not jobs_data and not steps_data:
                jobs_data, steps_data = await asyncio.gather(
                    self._jobs_from_runner(runner),
                    self._steps_from_runner(runner),
                )
                memo["jobs_data"] = jobs_data
                memo["steps_data"] = steps_data
            support_funcs["jobs"] = jobs_data
            support_funcs["steps"] = steps_data

        memo["support_funcs"] = support_funcs
        return support_funcs

    async def _jobs_from_runner(self, runner: Any) -> dict[str, Any]:
        container = self._find_container_with_child_attr(runner, "jid")
        if not container:
            return {}

        jobs: dict[str, Any] = {}
        # Parallelize registry lookups across all child runners
        tasks = [
            self._collect_job_output(child, jobs)
            for child in getattr(container, "_runners", {}).values()
        ]
        await asyncio.gather(*tasks)
        return jobs

    async def _collect_job_output(self, runner: Any, jobs: dict[str, Any]) -> None:
        model = getattr(runner, "model", None)
        children = list(getattr(runner, "_runners", {}).values())

        # Collect all (job_id, runner) pairs that need registry lookups
        targets: list[tuple[str, Any]] = []
        if model is not None and hasattr(model, "jid"):
            job_id = getattr(model, "jid", None) or getattr(
                model, "original_job_id", ""
            )
            if job_id:
                targets.append((job_id, runner))

        for child in children:
            child_model = getattr(child, "model", None)
            if child_model is None or not hasattr(child_model, "jid"):
                continue
            job_id = getattr(child_model, "jid", None) or getattr(
                child_model, "original_job_id", ""
            )
            if not job_id:
                continue
            targets.append((job_id, child))

        if not targets:
            return

        # Batch all reg_get calls in parallel instead of sequential N+1
        results = await asyncio.gather(
            *(r.reg_get(RunnerRegistryKeys.OUTPUTS) for _, r in targets)
        )
        # Dict updates between awaits are safe in asyncio's single-threaded model
        for (job_id, _), outputs in zip(targets, results, strict=True):
            jobs[job_id] = {"outputs": outputs or {}}

    async def _steps_from_runner(self, runner: Any) -> _StepAccessor:
        container = self._find_container_with_child_attr(runner, "step_index")
        if not container:
            return _StepAccessor()

        # Collect targets needing registry lookups
        targets: list[tuple[Any, Any]] = []
        for child in getattr(container, "_runners", {}).values():
            model = getattr(child, "model", None)
            if model is None or not hasattr(model, "step_index"):
                continue
            targets.append((model, child))

        if not targets:
            return _StepAccessor()

        # Batch all reg_get calls in parallel instead of sequential N+1
        results = await asyncio.gather(
            *(child.reg_get(RunnerRegistryKeys.OUTPUTS) for _, child in targets)
        )

        steps = _StepAccessor()
        for (model, _), raw in zip(targets, results, strict=True):
            outputs = {"typed_outputs": [], **(raw or {})}
            entry = {
                "index": getattr(model, "step_index", None),
                "name": getattr(model, "name", None),
                "outputs": outputs,
            }
            name = getattr(model, "name", None)
            if name:
                steps[name] = entry
            # Also allow numeric index access
            idx = getattr(model, "step_index", None)
            if idx is not None:
                steps[str(idx)] = entry

        return steps

    def _find_container_with_child_attr(self, runner: Any, attr: str) -> Any | None:
        current = runner
        while current is not None:
            children = getattr(current, "_runners", None)
            if children:
                for child in children.values():
                    model = getattr(child, "model", None)
                    if model is not None and hasattr(model, attr):
                        return current
            current = getattr(current, "parent", None)
        return None

    def clear_cache(self) -> None:
        """Clear the template cache and reset counters."""
        self._template_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        self._support_funcs_cache = None

    def cache_info(self) -> dict[str, int]:
        """Return cache statistics for debugging.

        Returns:
            Dict with ``hits``, ``misses``, ``size``, ``maxsize``.
        """
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "size": len(self._template_cache),
            "maxsize": self._template_cache_max_size,
        }
