"""Template resolver for Jinja2-based workflow templates"""

import asyncio
import json
import logging
import threading
from collections import OrderedDict
from typing import Any, Self

from jinja2 import Environment
from pydantic import BaseModel

from ofx.runner.metadata import ModelContext
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
            return await self._resolved_mapping_values(value, context_vars, memo)
        if isinstance(value, list):
            return await self._resolved_sequence_items(value, context_vars, memo)
        if issubclass(type(value), BaseModel):
            return value.model_copy(
                update=await self._resolved_model_values(value, context_vars, memo)
            )
        if not isinstance(value, (str, int, float, bool, dict, list)):
            return value

        value_str = str(value)
        if not self._contains_template_syntax(value_str):
            return value

        # Circular reference detection
        resolve_stack: list[str] = memo.setdefault("_resolve_stack", [])
        if value_str in resolve_stack:
            chain = " → ".join(resolve_stack + [value_str])
            raise ValueError(f"Circular template reference detected: {chain}")
        resolve_stack.append(value_str)

        support_funcs = await self._build_support_functions(context_vars, memo)
        template = self._cached_template(value_str)
        template_vars = self._template_vars(context_vars, support_funcs)

        try:
            result = await self._render_template(
                template,
                template_vars,
                value_str=value_str,
                context_vars=context_vars,
            )
        except Exception as e:
            raise e

        resolve_stack.pop()
        return self._coerce_scalar_result(value, result, value_str)

    async def _resolved_sequence_items(
        self,
        items: list[Any],
        context_vars: dict[str, Any],
        memo: dict[str, Any],
    ) -> list[Any]:
        return [await self.resolve(item, context_vars, memo) for item in items]

    async def _resolved_mapping_values(
        self,
        mapping: dict[Any, Any],
        context_vars: dict[str, Any],
        memo: dict[str, Any],
    ) -> dict[Any, Any]:
        return {
            key: await self.resolve(item, context_vars, memo)
            for key, item in mapping.items()
        }

    async def _resolved_model_values(
        self,
        model: BaseModel,
        context_vars: dict[str, Any],
        memo: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._resolved_mapping_values(dict(model), context_vars, memo)

    @staticmethod
    def _contains_template_syntax(value_str: str) -> bool:
        return "{{" in value_str or "{%" in value_str

    def _cached_template(self, value_str: str):
        _ensure_filters_registered(_jinja_env)

        if value_str in self._template_cache:
            self._template_cache.move_to_end(value_str)
            self._cache_hits += 1
            return self._template_cache[value_str]

        self._cache_misses += 1
        if len(self._template_cache) >= self._template_cache_max_size:
            self._template_cache.popitem(last=False)
        template = _jinja_env.from_string(value_str)
        self._template_cache[value_str] = template
        return template

    @staticmethod
    def _template_vars(
        context_vars: dict[str, Any],
        support_funcs: dict[str, Any],
    ) -> dict[str, Any]:
        template_vars = context_vars.copy()
        template_vars.update(support_funcs)
        return template_vars

    async def _render_template(
        self,
        template: Any,
        template_vars: dict[str, Any],
        *,
        value_str: str,
        context_vars: dict[str, Any],
    ) -> str:
        try:
            return await template.render_async(template_vars)
        except Exception as exc:
            raise self._template_render_error(
                exc,
                value_str=value_str,
                template_vars=template_vars,
                context_vars=context_vars,
            ) from exc

    @staticmethod
    def _template_preview(value_str: str, context_vars: dict[str, Any]) -> str:
        preview = value_str[:120] + ("…" if len(value_str) > 120 else "")
        secrets_dict = context_vars.get("secrets")
        if isinstance(secrets_dict, dict):
            for secret_val in secrets_dict.values():
                secret = str(secret_val)
                if len(secret) >= 4:
                    preview = preview.replace(secret, "***")
        return preview

    @staticmethod
    def _available_template_variables(template_vars: dict[str, Any]) -> list[str]:
        return sorted(
            key for key in template_vars if not key.startswith("_") and key != "secrets"
        )

    def _template_render_error(
        self,
        exc: Exception,
        *,
        value_str: str,
        template_vars: dict[str, Any],
        context_vars: dict[str, Any],
    ) -> Exception:
        preview = self._template_preview(value_str, context_vars)
        available = self._available_template_variables(template_vars)
        return type(exc)(
            f"Template rendering failed: {exc}\n"
            f"  Template: {preview}\n"
            f"  Available variables: {', '.join(available[:20])}"
        )

    def _coerce_scalar_result(self, original: Any, result: str, value_str: str) -> Any:
        if isinstance(original, bool):
            return result.lower() in ("true", "yes", "1", "t", "y")
        if isinstance(original, int):
            return self._coerce_numeric_result(
                result,
                value_str,
                cast=int,
                label="integer",
            )
        if isinstance(original, float):
            return self._coerce_numeric_result(
                result,
                value_str,
                cast=float,
                label="float",
            )
        return result

    @staticmethod
    def _coerce_numeric_result(
        result: str,
        value_str: str,
        *,
        cast,
        label: str,
    ) -> Any:
        try:
            return cast(result)
        except ValueError:
            _logger.debug(
                "Template returned non-%s '%s', keeping as string (template: %s)",
                label,
                result[:50],
                value_str[:80],
            )
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
            jobs_data, steps_data = await self._runner_support_values(runner, memo)
            support_funcs.update({"jobs": jobs_data, "steps": steps_data})

        memo["support_funcs"] = support_funcs
        return support_funcs

    async def _runner_support_values(
        self,
        runner: Any,
        memo: dict[str, Any],
    ) -> tuple[dict[str, Any], _StepAccessor]:
        if "jobs_data" not in memo or "steps_data" not in memo:
            jobs_data: dict[str, Any] = {}
            steps_data = _StepAccessor()
            job_container = None
            step_container = None
            current = runner

            while current is not None and (job_container is None or step_container is None):
                children = list(getattr(current, "_runners", {}).values())
                if job_container is None and any(
                    getattr(getattr(child, "model", None), "jid", None) is not None
                    for child in children
                ):
                    job_container = current
                if step_container is None and any(
                    getattr(getattr(child, "model", None), "step_index", None)
                    is not None
                    for child in children
                ):
                    step_container = current
                current = getattr(current, "parent", None)

            if job_container is not None:
                job_targets: list[tuple[str, Any]] = []
                for job_runner in getattr(job_container, "_runners", {}).values():
                    for candidate in (
                        job_runner,
                        *getattr(job_runner, "_runners", {}).values(),
                    ):
                        model = getattr(candidate, "model", None)
                        if model is None:
                            continue
                        model_context = ModelContext.from_model(model)
                        job_id = model_context.jid or getattr(
                            model,
                            "original_job_id",
                            "",
                        )
                        if job_id:
                            job_targets.append((job_id, candidate))

                if job_targets:
                    job_results = await self._registry_outputs(job_targets)
                    jobs_data = {
                        job_id: {"outputs": outputs or {}}
                        for (job_id, _), outputs in zip(
                            job_targets,
                            job_results,
                            strict=True,
                        )
                    }

            if step_container is not None:
                step_targets: list[tuple[Any, Any]] = []
                for child in getattr(step_container, "_runners", {}).values():
                    model = getattr(child, "model", None)
                    model_context = ModelContext.from_model(model)
                    if model is None or model_context.step_index is None:
                        continue
                    step_targets.append((model, child))

                if step_targets:
                    step_results = await self._registry_outputs(step_targets)
                    for (model, _), raw in zip(
                        step_targets,
                        step_results,
                        strict=True,
                    ):
                        outputs = {"typed_outputs": [], **(raw or {})}
                        model_context = ModelContext.from_model(model)
                        entry = {
                            "index": model_context.step_index,
                            "name": model_context.name,
                            "outputs": outputs,
                        }
                        if entry["name"]:
                            steps_data[entry["name"]] = entry
                        if entry["index"] is not None:
                            steps_data[str(entry["index"])] = entry

            memo["jobs_data"] = jobs_data
            memo["steps_data"] = steps_data
        jobs_data = memo["jobs_data"]
        steps_data = memo["steps_data"]
        return jobs_data, steps_data

    async def _registry_outputs(self, targets: list[tuple[Any, Any]]) -> list[Any]:
        return await asyncio.gather(
            *(runner.reg_get(RunnerRegistryKeys.OUTPUTS) for _, runner in targets)
        )

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
