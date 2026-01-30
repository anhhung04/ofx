"""Template resolver for Jinja2-based workflow templates"""

import os
import shutil
from pathlib import Path
from typing import Any

from jinja2 import Template
from pydantic import BaseModel

from ofx.runner.core.registry_keys import RunnerRegistryKeys
from ofx.settings import TEMP_DIR, TOOLS_BIN_DIR, TOOLS_DIR


class TemplateResolver:
    """Handles template resolution with caching and optimization"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._template_cache: dict[str, Template] = {}
        self._support_funcs_cache: dict[str, Any] | None = None
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

        support_funcs = self.get_support_functions()

        # Add registry-based data for accessing job and step data
        if "registry" in context_vars:
            registry = context_vars["registry"]
            jobs_data: dict[str, Any] = {}
            steps_data: list[dict[str, Any]] = []

            runner = context_vars.get("runner")
            if runner is not None:
                jobs_data = await self._jobs_from_runner(runner)
                steps_data = await self._steps_from_runner(runner)

            # Fallbacks for legacy registry usage
            if not jobs_data:
                jobs_data = await registry.get("jobs:results") or {}
            if not steps_data and "current_job_id" in context_vars:
                job_id = context_vars["current_job_id"]
                step_results = await registry.get(f"jobs:{job_id}:steps") or {}
                steps_data = list(step_results.values())

            support_funcs["jobs"] = jobs_data
            support_funcs["steps"] = steps_data

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

    def get_support_functions(self) -> dict[str, Any]:
        """Get template support functions with caching"""

        def _read_file(path: str) -> str:
            file_path = Path(path)
            if not file_path.exists():
                return ""
            return file_path.read_text()

        def _write_file(path: str, content: str) -> None:
            file_path = Path(path)
            file_path.write_text(content)

        if self._support_funcs_cache is None:
            sudo = "sudo" if os.geteuid() != 0 and shutil.which("sudo") else ""
            tools_dir_str = str(TOOLS_DIR.absolute())
            tools_bin_dir_str = str(TOOLS_BIN_DIR.absolute())

            self._support_funcs_cache = {
                "sudo": sudo,
                "tools_dir": tools_dir_str,
                "tools_bin_dir": tools_bin_dir_str,
                "temp_dir": TEMP_DIR.absolute().as_posix(),
                "fapt": lambda app: f'if [ -z "$( ls -A /var/lib/apt/lists/ )" ]; then {sudo} apt-get update; fi && {sudo} apt-get install -y --no-install-recommends {app}',
                "uv_install": lambda name: f"uv tool install --python-preference managed --force --reinstall {name}",
                "go_install": lambda pkg: f"GO111MODULE=on GOBIN={tools_bin_dir_str} go install {pkg}@latest",
                "cargo_install": lambda name: f"cargo install --root {tools_dir_str} {name}",
                "npm_install": lambda name: f"npm install -g --prefix {tools_dir_str} {name}",
                "static_install": lambda url, name=None: (
                    f"curl -fSsL {url} -o {tools_bin_dir_str}/{name if name else Path(url).name} && chmod +x {tools_bin_dir_str}/{name if name else Path(url).name}"
                ),
                "file_read": _read_file,
                "file_write": _write_file,
                "file_exists": lambda path: Path(path).exists(),
                "python": __import__("sys").executable,
                "pip_install": lambda pkg: f'"{__import__("sys").executable}" -m pip install --upgrade {pkg}',
            }

        support_funcs = self._support_funcs_cache.copy()

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

    async def _steps_from_runner(self, runner: Any) -> list[dict[str, Any]]:
        container = self._find_container_with_child_attr(runner, "step_index")
        if not container:
            return []

        steps: list[dict[str, Any]] = []
        for child in getattr(container, "_runners", {}).values():
            model = getattr(child, "model", None)
            if model is None or not hasattr(model, "step_index"):
                continue
            outputs = await child.reg_get(RunnerRegistryKeys.OUTPUTS) or {}
            steps.append(
                {
                    "index": getattr(model, "step_index", None),
                    "name": getattr(model, "name", None),
                    "outputs": outputs,
                }
            )

        steps.sort(key=lambda item: item.get("index") or 0)
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
