"""Template resolver for Jinja2-based workflow templates"""

from typing import Any

from jinja2 import Template
from pydantic import BaseModel

from ofx.runner.templates.helpers import TemplateHelpers


class TemplateResolver:
    """Handles template resolution with caching and optimization"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._template_cache: dict[str, Template] = {}
        self._template_cache_max_size = 1000

    async def resolve(
        self,
        value: Any,
        context_vars: dict[str, Any],
    ) -> Any:
        """Resolve Jinja2 templates in values recursively with optimized caching
        Args:
            value: Value to resolve (can be str, dict, list, primitives)
            context_vars: Context variables for template rendering
        Returns:
            Resolved value with templates expanded
        """
        if value is None:
            return value
        elif isinstance(value, dict):
            return {k: await self.resolve(v, context_vars) for k, v in value.items()}
        elif isinstance(value, list):
            return [await self.resolve(v, context_vars) for v in value]
        elif issubclass(type(value), BaseModel):
            return value.model_copy(
                update={k: await self.resolve(v, context_vars) for k, v in value}
            )
        elif not isinstance(value, (str, int, float, bool, dict, list)):
            return value

        value_str = str(value)
        if "{{" not in value_str and "{%" not in value_str:
            return value

        support_funcs = TemplateHelpers.get_support_functions(
            context_vars.get("envs", {})
        )

        # Add registry-based data for accessing job and step data
        if "registry" in context_vars:
            registry = context_vars["registry"]
            job_results = await registry.get("jobs:results") or {}

            # Get steps for current job if available
            steps_list = []
            if "current_job_id" in context_vars:
                job_id = context_vars["current_job_id"]
                step_results = await registry.get(f"jobs:{job_id}:steps") or {}
                sorted_steps = step_results.items()
                steps_list = [data for idx, data in sorted_steps]

            support_funcs["jobs"] = job_results
            support_funcs["steps"] = steps_list

        if value_str not in self._template_cache:
            if len(self._template_cache) >= self._template_cache_max_size:
                first_key = next(iter(self._template_cache))
                del self._template_cache[first_key]
            self._template_cache[value_str] = Template(
                value_str,
                enable_async=True,
            )

        template = self._template_cache[value_str]

        template_vars = context_vars.copy()
        template_vars.update(support_funcs)

        result = await template.render_async(template_vars)

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

    def clear_cache(self):
        """Clear the template cache"""
        self._template_cache.clear()
