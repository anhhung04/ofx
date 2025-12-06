import logging
import os
import shutil
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import Template
from pydantic import BaseModel, Field

from ofx.models.job import Job
from ofx.models.step import Step
from ofx.models.workflow import Workflow
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class RunnerStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunContext(BaseModel):
    inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Inputs for the workflow run, can be used to pass parameters",
    )
    secrets: Dict[str, Any] = Field(
        default_factory=dict,
        description="Secrets for the workflow run, can be used to pass sensitive information",
    )
    envs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Environment variables for the workflow run",
    )
    output_path: Path = Field(
        default=Path.cwd() / "out",
        description="Path to store output files",
    )
    vars: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context variables for the workflow run",
    )


class RunResult(BaseModel):
    status: RunnerStatus
    error: Optional[str] = None
    outputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Outputs produced by the run",
    )
    name: str = Field(..., description="Name of the run")
    run_id: str = Field(..., description="Unique identifier for the run")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for the run",
    )


class BaseRunner:
    def __init__(
        self, name: Any, ctx: RunContext, parent: Optional["BaseRunner"] = None
    ):
        name = str(name)
        self._id = f"{name}-{str(uuid.uuid4())}"
        self._status = RunnerStatus.IDLE
        self._ctx = ctx
        self._parent = parent
        self._error = None
        self._model = None
        self._result = RunResult(status=self.status, run_id=self._id, name=name)

    async def run(self):
        """Run the workflow and return the result."""
        try:
            self._status = RunnerStatus.IDLE
            self._ctx.vars.update({"self": self.model})
            await self._pre_run()
        except Exception as e:
            self._error = f"Pre-run error: {str(e)}"
            self._status = RunnerStatus.FAILED
            return self.get_result()

        try:
            self._status = RunnerStatus.RUNNING
            await self._do_run()
        except Exception as e:
            self._error = f"Run error: {str(e)}"
            self._status = RunnerStatus.FAILED
            return self.get_result()

        try:
            await self._post_run()
            self._status = RunnerStatus.COMPLETED
        except Exception as e:
            self._error = f"Post-run error: {str(e)}"
            self._status = RunnerStatus.FAILED
        return self.get_result()

    async def _do_run(self):
        raise NotImplementedError("Subclasses should implement _do_run method.")

    async def _pre_run(self):
        raise NotImplementedError("Subclasses should implement _pre_run method.")

    async def _post_run(self):
        raise NotImplementedError("Subclasses should implement _post_run method.")

    def _resolve_template(self, value: Any) -> Any:
        """
        Resolve Jinja2 templates in string values and convert back to the original type.

        Args:
            value: The value that may contain a template
            vars: Additional variables to include in the template context

        Returns:
            The resolved value, maintaining the original type if possible
        """
        if value is None or not isinstance(value, (str, int, float, bool, dict, list)):
            return value
        if type(value) is dict:
            return {k: self._resolve_template(v) for k, v in value.items()}
        elif type(value) is list:
            return [self._resolve_template(v) for v in value]
        try:
            string_value = str(value)
            sudo = "sudo" if os.geteuid() != 0 and shutil.which("sudo") else ""
            SUPPORT_FUNCS = {
                "sudo": sudo,
                "run_id": self._id,
                "fapt": f'if [ -z "$( ls -A /var/lib/apt/lists/ )" ]; then {sudo} apt-get update; fi && {sudo} apt-get install -y --no-install-recommends',
                "uv_install": "uv tool install",
                "go_install": "go install -v",
                "file_read": lambda path: (
                    Path(path).read_text() if Path(path).exists() else None
                ),
                "file_exists": lambda path: Path(path).exists(),
            }
            if "${{" not in string_value and "{%" not in string_value:
                return value
            template = Template(
                string_value, variable_start_string="${{", variable_end_string="}}"
            )
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
                    logger.warning(
                        self._produce_log(
                            f"Could not convert template result '{result}' back to integer"
                        )
                    )
                    return result
            elif isinstance(value, float):
                try:
                    return float(result)
                except ValueError:
                    logger.warning(
                        self._produce_log(
                            f"Could not convert template result '{result}' back to float"
                        )
                    )
                    return result

            logger.debug(
                self._produce_log(
                    f"Resolved template for value \n----\n{value}\n----\n to: \n----\n{result}\n----\n"
                )
            )
            return result

        except Exception as e:
            logger.error(
                self._produce_log(
                    f"Error resolving template for value \n----\n{value}\n----\n: {e}"
                )
            )
            return value

    def _resolve_template_fields(self, fields: list[str]):
        if not self.model:
            return
        for field in fields:
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
        return self._status in {
            RunnerStatus.COMPLETED,
            RunnerStatus.FAILED,
        }

    @property
    def is_success(self) -> bool:
        return self._status == RunnerStatus.COMPLETED and self._error is None

    @property
    def run_id(self) -> str:
        return self._id

    def get_result(self) -> RunResult:
        """
        Get the result of the workflow run.
        """
        self._result.status = self.status
        self._result.error = self._error
        return self._result

    @property
    def ctx_vars(self) -> RunContext:
        """
        Get the context variables for the workflow run.
        """
        return self._ctx

    @property
    def parent(self) -> "BaseRunner | None":
        return self._parent
