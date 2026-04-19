"""Template resolver for Jinja2-based workflow templates"""

import json
import logging
import threading
from typing import Any

from jinja2 import Environment
from pydantic import BaseModel

from ofx.runner.core.registry_keys import RunnerRegistryKeys

_logger = logging.getLogger("ofx.templates")
_resolver_lock = threading.Lock()


def _tojson_python(value: Any, indent: int | None = None) -> str:
    """JSON serialization that outputs Python-compatible literals.

    Replaces JSON ``true``/``false``/``null`` with Python's
    ``True``/``False``/``None`` so the output can be used directly
    in inline ``script:`` blocks.
    """
    raw = json.dumps(value, indent=indent, default=str)
    # Replace JSON booleans/null with Python equivalents.
    # Only replace standalone tokens, not substrings inside strings.
    # json.dumps quotes string values, so bare true/false/null are safe to replace.
    raw = raw.replace(": true", ": True")
    raw = raw.replace(": false", ": False")
    raw = raw.replace(": null", ": None")
    raw = raw.replace("[true", "[True")
    raw = raw.replace("[false", "[False")
    raw = raw.replace("[null", "[None")
    raw = raw.replace(", true", ", True")
    raw = raw.replace(", false", ", False")
    raw = raw.replace(", null", ", None")
    return raw


def _build_jinja_env() -> Environment:
    """Create a Jinja2 Environment with Python-safe ``tojson`` filter."""
    env = Environment(enable_async=True)
    env.filters["tojson"] = _tojson_python
    return env


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

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            with _resolver_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._template_cache = {}
                    inst._support_funcs_cache = None
                    inst._template_cache_max_size = 1000
                    cls._instance = inst
        return cls._instance

    def __init__(self):
        # Initialization moved to __new__ to avoid resetting on repeated calls
        pass

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
        elif isinstance(value, dict):
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

        if value_str not in self._template_cache:
            if len(self._template_cache) >= self._template_cache_max_size:
                first_key = next(iter(self._template_cache))
                del self._template_cache[first_key]
            self._template_cache[value_str] = _jinja_env.from_string(value_str)

        template = self._template_cache[value_str]

        template_vars = context_vars.copy()
        template_vars.update(support_funcs)

        try:
            result = await template.render_async(template_vars)
        except Exception as e:
            # Provide actionable context for template errors
            preview = value_str[:120] + ("…" if len(value_str) > 120 else "")
            raise type(e)(
                f"Template rendering failed: {e}\n"
                f"  Template: {preview}"
            ) from e

        resolve_stack.pop()

        if isinstance(value, bool):
            return result.lower() in ("true", "yes", "1", "t", "y")
        elif isinstance(value, int):
            try:
                return int(result)
            except ValueError:
                return result
        elif isinstance(value, float):
            try:
                return float(result)
            except ValueError:
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

        # Add registry-based data for accessing job and step data
        if "registry" in context_vars:
            registry = context_vars["registry"]
            jobs_data: dict[str, Any] = memo.get("jobs_data", {})
            steps_data: dict[str, Any] = memo.get("steps_data", {})

            runner = context_vars.get("runner")
            if runner is not None and not jobs_data and not steps_data:
                jobs_data = await self._jobs_from_runner(runner)
                steps_data = await self._steps_from_runner(runner)
                memo["jobs_data"] = jobs_data
                memo["steps_data"] = steps_data

            # Fallbacks for legacy registry usage
            if not jobs_data:
                jobs_data = await registry.get("jobs:results") or {}
                memo["jobs_data"] = jobs_data
            if not steps_data and "current_job_id" in context_vars:
                job_id = context_vars["current_job_id"]
                step_results = await registry.get(f"jobs:{job_id}:steps") or {}
                steps_data = dict(step_results)
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
        for child in getattr(container, "_runners", {}).values():
            await self._collect_job_output(child, jobs)
        return jobs

    async def _collect_job_output(self, runner: Any, jobs: dict[str, Any]) -> None:
        model = getattr(runner, "model", None)
        if model is not None and hasattr(model, "jid"):
            job_id = getattr(model, "jid", None) or getattr(
                model, "original_job_id", ""
            )
            if job_id:
                outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS) or {}
                jobs[job_id] = {"outputs": outputs}

        for child in getattr(runner, "_runners", {}).values():
            model = getattr(child, "model", None)
            if model is None or not hasattr(model, "jid"):
                continue
            job_id = getattr(model, "jid", None) or getattr(
                model, "original_job_id", ""
            )
            if not job_id:
                continue
            outputs = await child.reg_get(RunnerRegistryKeys.OUTPUTS) or {}
            jobs[job_id] = {"outputs": outputs}

    async def _steps_from_runner(self, runner: Any) -> _StepAccessor:
        container = self._find_container_with_child_attr(runner, "step_index")
        if not container:
            return _StepAccessor()

        steps = _StepAccessor()
        for child in getattr(container, "_runners", {}).values():
            model = getattr(child, "model", None)
            if model is None or not hasattr(model, "step_index"):
                continue
            raw = await child.reg_get(RunnerRegistryKeys.OUTPUTS) or {}
            outputs = {"typed_outputs": [], **raw}
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

    def clear_cache(self):
        """Clear the template cache"""
        self._template_cache.clear()
        if self._support_funcs_cache:
            self._support_funcs_cache.clear()
