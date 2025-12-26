import logging
import os
import shutil
from pathlib import Path
from typing import Any, TYPE_CHECKING
from jinja2 import Template

from ofx.runner.core.models import RunContext
from ofx.settings import settings

if TYPE_CHECKING:
    from ofx.runner.base import BaseRunner

logger = logging.getLogger(settings.app_branding)


class TemplateEngine:
    def __init__(self, runner: "BaseRunner"):
        self._runner = runner
    
    @staticmethod
    def _convert_to_bool(value: str) -> bool:
        """Convert string to boolean."""
        return value.lower() in ("true", "yes", "1", "t", "y")
    
    @staticmethod
    def _convert_to_int(value: str, original: int, logger_func) -> int | str:
        """Convert string to int with fallback."""
        try:
            return int(value)
        except ValueError:
            logger.warning(
                logger_func(
                    f"Could not convert template result '{value}' back to integer"
                )
            )
            return value
    
    @staticmethod
    def _convert_to_float(value: str, original: float, logger_func) -> float | str:
        """Convert string to float with fallback."""
        try:
            return float(value)
        except ValueError:
            logger.warning(
                logger_func(
                    f"Could not convert template result '{value}' back to float"
                )
            )
            return value

    def resolve(self, value: Any) -> Any:
        if value is None or not isinstance(value, (str, int, float, bool, dict, list)):
            return value
        if type(value) is dict:
            return {k: self.resolve(v) for k, v in value.items()}
        elif type(value) is list:
            return [self.resolve(v) for v in value]
        try:
            string_value = str(value)
            sudo = "sudo" if os.geteuid() != 0 and shutil.which("sudo") else ""
            SUPPORT_FUNCS = {
                "sudo": sudo,
                "run_id": self._runner.run_id,
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
            template_vars = self._runner.ctx_vars.model_dump(exclude={"vars"})
            template_vars.update(SUPPORT_FUNCS)

            if self._runner.ctx_vars.vars:
                template_vars.update(self._runner.ctx_vars.vars)

            result = template.render(template_vars)

            if isinstance(value, bool):
                return self._convert_to_bool(result)
            elif isinstance(value, int):
                return self._convert_to_int(result, value, self._produce_log)
            elif isinstance(value, float):
                return self._convert_to_float(result, value, self._produce_log)

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

    def resolve_model_fields(self, model: Any, fields: list[str]):
        if not model:
            return
        for field in fields:
            resolved_value = self.resolve(getattr(model, field))
            setattr(model, field, resolved_value)

    def _produce_log(self, message: Any) -> str:
        """Delegate logging to runner."""
        return self._runner._produce_log(message)
