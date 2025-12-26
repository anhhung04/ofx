"""Base runner class for workflow, job, and step execution"""

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from jinja2 import Template

from ofx.models.workflow import Workflow
from ofx.models.job import Job
from ofx.models.step import Step
from ofx.runner.models import RunnerStatus, RunContext, RunResult
from ofx.settings import settings, TOOLS_DIR, TOOLS_BIN_DIR

if TYPE_CHECKING:
    from ofx.runner.base import BaseRunner

logger = logging.getLogger(settings.app_branding)


class BaseRunner:
    """Abstract base class for all runners (workflow, job, step, command)"""
    
    # Cache for compiled templates (limit size to prevent memory bloat)
    _template_cache = {}
    _template_cache_max_size = 1000
    _support_funcs_cache = None

    def __init__(self, name: Any, ctx: RunContext, parent: Optional["BaseRunner"] = None):
        name = str(name)
        self._id = f"{name}-{str(uuid.uuid4())}"
        self._status = RunnerStatus.IDLE
        self._ctx = ctx
        self._parent = parent
        self._error = None
        self._model = None
        self._result = RunResult(status=self.status, run_id=self._id, name=name)

    async def run(self) -> RunResult:
        """Execute the runner's lifecycle: pre_run -> do_run -> post_run"""
        try:
            self._status = RunnerStatus.IDLE
            self._ctx.vars.update({"self": self.model})
            await self._pre_run()
        except Exception as e:
            self._error = f"Pre-run error: {str(e)}"
            self._status = RunnerStatus.FAILED
            logger.error(self._produce_log(self._error))
            return self.get_result()
        
        try:
            self._status = RunnerStatus.RUNNING
            await self._do_run()
        except Exception as e:
            self._error = f"Run error: {str(e)}"
            self._status = RunnerStatus.FAILED
            logger.error(self._produce_log(self._error))
            return self.get_result()
        
        try:
            await self._post_run()
            self._status = RunnerStatus.COMPLETED
        except Exception as e:
            self._error = f"Post-run error: {str(e)}"
            self._status = RunnerStatus.FAILED
            logger.error(self._produce_log(self._error))
        
        return self.get_result()

    async def _do_run(self):
        raise NotImplementedError("Subclasses should implement _do_run method.")

    async def _pre_run(self):
        raise NotImplementedError("Subclasses should implement _pre_run method.")

    async def _post_run(self):
        raise NotImplementedError("Subclasses should implement _post_run method.")

    def _resolve_template(self, value: Any) -> Any:
        """Resolve Jinja2 templates in values recursively"""
        if value is None or not isinstance(value, (str, int, float, bool, dict, list)):
            return value
        if isinstance(value, dict):
            return {k: self._resolve_template(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_template(v) for v in value]
        string_value = str(value)
        if "${{" not in string_value and "{%" not in string_value:
            return value
        
        try:
            # Use cached SUPPORT_FUNCS if available
            if BaseRunner._support_funcs_cache is None:
                sudo = "sudo" if os.geteuid() != 0 and shutil.which("sudo") else ""
                BaseRunner._support_funcs_cache = {
                    "sudo": sudo,
                    "tools_dir": str(TOOLS_DIR.absolute()),
                    "tools_bin_dir": str(TOOLS_BIN_DIR.absolute()),
                    "fapt": f'if [ -z "$( ls -A /var/lib/apt/lists/ )" ]; then {sudo} apt-get update; fi && {sudo} apt-get install -y --no-install-recommends',
                    "uv_install": lambda name: f"uv tool install --python-preference managed --force --reinstall {name}",
                    "go_install": lambda pkg: f"GO111MODULE=on GOBIN={TOOLS_BIN_DIR} go install {pkg}@latest",
                    "cargo_install": lambda name: f"cargo install --root {TOOLS_DIR} {name}",
                    "npm_install": lambda name: f"npm install -g --prefix {TOOLS_DIR} {name}",
                    "static_install": lambda url, name=None: (
                        f"curl -fSsL {url} -o {TOOLS_BIN_DIR / (name if name else Path(url).name)} && chmod +x {TOOLS_BIN_DIR / (name if name else Path(url).name)}"
                    ),
                    "file_read": lambda path: (Path(path).read_text() if Path(path).exists() else None),
                    "file_write": lambda path, content: Path(path).write_text(content),
                    "file_exists": lambda path: Path(path).exists(),
                    "env": lambda var, default="": os.getenv(var, default),
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": lambda v: str(v).lower() in ("true", "yes", "1", "t", "y"),
                }
            
            # Add run_id dynamically (unique per runner instance)
            SUPPORT_FUNCS = BaseRunner._support_funcs_cache.copy()
            SUPPORT_FUNCS["run_id"] = self._id
            
            # Use template cache for repeated templates
            if string_value not in BaseRunner._template_cache:
                # Clear cache if it gets too large (simple LRU-like behavior)
                if len(BaseRunner._template_cache) >= BaseRunner._template_cache_max_size:
                    BaseRunner._template_cache.clear()
                    
                BaseRunner._template_cache[string_value] = Template(
                    string_value, variable_start_string="${{", variable_end_string="}}"
                )
            
            template = BaseRunner._template_cache[string_value]
            template_vars = self.ctx_vars.model_dump(exclude={"vars"})
            template_vars.update(SUPPORT_FUNCS)
            if self.ctx_vars.vars:
                template_vars.update(self._ctx.vars)
            
            result = template.render(template_vars)
            if isinstance(value, bool):
                return result.lower() in ("true", "yes", "1", "t", "y")
            elif isinstance(value, int):
                try:
                    return int(result)
                except ValueError:
                    logger.warning(self._produce_log(f"Could not convert template result '{result}' back to integer"))
                    return result
            elif isinstance(value, float):
                try:
                    return float(result)
                except ValueError:
                    logger.warning(self._produce_log(f"Could not convert template result '{result}' back to float"))
                    return result
            
            logger.debug(self._produce_log(f"Resolved template: {value} -> {result}"))
            return result
        except Exception as e:
            logger.error(self._produce_log(f"Error resolving template for value '{value}': {e}"))
            return value

    def _resolve_template_fields(self, fields: list[str]) -> None:
        """Resolve templates in specific model fields"""
        if not self.model:
            return
        for field in fields:
            if hasattr(self.model, field):
                resolved_value = self._resolve_template(getattr(self.model, field))
                setattr(self._model, field, resolved_value)

    def _produce_log(self, message: Any) -> str:
        raise NotImplementedError("Subclasses should implement _produce_log method.")

    @property
    def model(self) -> Workflow | Job | Step | None:
        return self._model

    @property
    def status(self) -> RunnerStatus:
        return self._status

    @property
    def is_finished(self) -> bool:
        return self._status in {RunnerStatus.COMPLETED, RunnerStatus.FAILED}

    @property
    def is_success(self) -> bool:
        return self._status == RunnerStatus.COMPLETED and self._error is None

    @property
    def run_id(self) -> str:
        return self._id

    def get_result(self) -> RunResult:
        self._result.status = self.status
        self._result.error = self._error
        return self._result

    @property
    def ctx_vars(self) -> RunContext:
        return self._ctx

    @property
    def parent(self) -> "BaseRunner | None":
        return self._parent
    
    def get_job_status(self, job_id: str) -> Optional[RunnerStatus]:
        """Get job status from registry (WorkflowRunner override)"""
        return None
    
    def get_job_from_registry(self, job_id: str) -> Optional[dict[str, Any]]:
        """Get job from registry (WorkflowRunner override)"""
        return None
