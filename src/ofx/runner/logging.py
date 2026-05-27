import logging
from dataclasses import dataclass

from ofx.settings import settings
from ofx.utils.log import reload_logging_config

_logger: logging.Logger | None = None


@dataclass(frozen=True)
class LogContext:
    run_id: str | None = None
    model_name: str | None = None
    model_jid: str | None = None
    step_index: int | str | None = None

    @property
    def prefix(self) -> str:
        parts: list[str] = []
        if self.run_id:
            parts.append(f"[RUN-{self.run_id}]")
        if self.model_name:
            parts.append(f"'{self.model_name}'")
        if self.model_jid:
            parts.append(f"'{self.model_jid}'")
        if self.step_index is not None:
            parts.append(f"'step{self.step_index}'")
        return " › ".join(parts)


def get_logger() -> logging.Logger:
    """Return a shared logger configured for OFX.

    The logger is a singleton keyed by the application branding from settings.
    On first call the logging configuration is (re)loaded via ``reload_logging_config``
    to ensure console handling and redaction filters are attached.
    Subsequent calls return the same ``logging.Logger`` instance.
    """
    global _logger
    if _logger is None:
        _logger = logging.getLogger(settings.app_branding)
        # Apply the standard OFX logging configuration (handlers, filters, etc.)
        reload_logging_config(settings)
    return _logger
