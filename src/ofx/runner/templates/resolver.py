"""Template resolver for Jinja2-based workflow templates"""

from pathlib import Path
from typing import Any

from jinja2 import Template

from ofx.runner.templates.helpers import TemplateHelpers


class TemplateResolver:
    """Handles template resolution with caching and optimization"""

    def __init__(self):
        self._template_cache: dict[str, Template] = {}
        self._template_cache_max_size = 1000

    async def resolve(
        self,
        value: Any,
        context_vars: dict[str, Any],
        run_id: str,
    ) -> Any:
        """Resolve Jinja2 templates in values recursively with optimized caching
        
        Args:
            value: Value to resolve (can be str, dict, list, primitives)
            context_vars: Context variables for template rendering
            run_id: Current runner ID
            
        Returns:
            Resolved value with templates expanded
        """
        if value is None or not isinstance(value, (str, int, float, bool, dict, list)):
            return value
            
        if isinstance(value, dict):
            return {k: await self.resolve(v, context_vars, run_id) for k, v in value.items()}
            
        if isinstance(value, list):
            return [await self.resolve(v, context_vars, run_id) for v in value]
            
        string_value = str(value)
        if "${{" not in string_value and "{%" not in string_value:
            return value

        # Get support functions
        support_funcs = TemplateHelpers.get_support_functions(
            context_vars.get("envs", {})
        )
        support_funcs["run_id"] = run_id

        # Cache template compilation
        if string_value not in self._template_cache:
            if len(self._template_cache) >= self._template_cache_max_size:
                first_key = next(iter(self._template_cache))
                del self._template_cache[first_key]
            self._template_cache[string_value] = Template(
                string_value,
                variable_start_string="${{",
                variable_end_string="}}",
                enable_async=True
            )

        template = self._template_cache[string_value]
        
        # Prepare template variables
        template_vars = context_vars.copy()
        template_vars.update(support_funcs)

        # Render template
        result = await template.render_async(template_vars)

        # Type conversion for non-string values
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
