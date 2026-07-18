from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterable, Mapping
from typing import Any

from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text

_MIN_REDACT_LEN = 4

_REDACTED = "***"

_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|credential"
    r"|auth|bearer|access[_-]?key|ssh[_-]?key|ssh[_-]?pass)",
    re.IGNORECASE,
)

class SecretRedactFilter(logging.Filter):
    """Logging filter that replaces registered secret values with ``***``.

    Usage::

        redact_filter.register_values({"my_api_key_value", "db_password"})
    """

    _instance: SecretRedactFilter | None = None
    _values: set[str]
    _pattern: re.Pattern[str] | None

    def __new__(cls) -> SecretRedactFilter:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._values = set()
            cls._instance._pattern = None
        return cls._instance

    @classmethod
    def get_instance(cls) -> SecretRedactFilter:
        return cls()

    def register_values(self, values: set[str]) -> None:
        """Add secret values to redact.  Ignores short/empty values."""
        new = {v for v in values if isinstance(v, str) and len(v) >= _MIN_REDACT_LEN}
        if new - self._values:
            self._values |= new
            self._rebuild_pattern()

    def register_dict(
        self, data: dict[str, Any], *, sensitive_only: bool = False
    ) -> None:
        """Register values from a dict (e.g. ctx.secrets or ctx.envs).

        Args:
            data: Key/value mapping.
            sensitive_only: If True, only register values whose key name
                matches a sensitive pattern (password, token, key, etc.).
        """
        for key, val in data.items():
            if not isinstance(val, str) or len(val) < _MIN_REDACT_LEN:
                continue
            if sensitive_only and not _SENSITIVE_KEY_RE.search(key):
                continue
            self._values.add(val)
        self._rebuild_pattern()

    def clear(self) -> None:
        """Remove all registered values (useful between test runs)."""
        self._values.clear()
        self._pattern = None

    def filter(self, record: logging.LogRecord) -> bool:
        if self._pattern and record.msg:
            record.msg = self._redact(record.msg)
        if record.args:
            record.args = self._redact_args(record.args)
        return True

    def _rebuild_pattern(self) -> None:
        if not self._values:
            self._pattern = None
            return
        escaped = sorted((re.escape(v) for v in self._values), key=len, reverse=True)
        self._pattern = re.compile("|".join(escaped))

    def _redact(self, text: Any) -> Any:
        if not isinstance(text, str) or not self._pattern:
            return text
        return self._pattern.sub(_REDACTED, text)

    def _redact_args(self, args: Any) -> Any:
        if isinstance(args, dict):
            return {
                k: self._redact(v) if isinstance(v, str) else v for k, v in args.items()
            }
        if isinstance(args, (tuple, list)):
            return tuple(self._redact(a) if isinstance(a, str) else a for a in args)
        return args

def register_secrets(secrets: Mapping[str, Any] | Iterable[Any]) -> None:
    """Register secret values for redaction from a mapping or iterable."""
    values = secrets.values() if isinstance(secrets, Mapping) else secrets
    SecretRedactFilter.get_instance().register_values(
        {str(value) for value in values if value}
    )

def register_sensitive_env(envs: dict[str, Any]) -> None:
    """Convenience: register env values whose keys look sensitive."""
    SecretRedactFilter.get_instance().register_dict(envs, sensitive_only=True)

class BeautifiedMetadataHandler(RichHandler):
    def __init__(self, *args, **kwargs):
        self._time_format = kwargs.get("log_time_format", "[%X]")
        super().__init__(*args, **kwargs)

    def emit(self, record):
        if not self.console:
            return super().emit(record)

        full_raw_msg = self.format(record)
        lines = full_raw_msg.splitlines()
        in_stream_block = False
        for raw_line in lines:
            line_text = Text.from_markup(raw_line)
            line_plain = line_text.plain

            is_header = any(x in line_plain for x in ["===stdout===", "===stderr==="])
            is_footer = "============" in line_plain

            if is_header:
                in_stream_block = True

            if is_footer:
                in_stream_block = False

            if in_stream_block:
                self.console.print(raw_line, highlight=False, markup=False)
            else:
                self._print_formatted(raw_line, record)

    def _print_formatted(self, line_text, record):
        """Prepends padded Time and Level to the left of the message."""
        if self.highlighter:
            message_text = self.highlighter(line_text)
        else:
            message_text = Text.from_markup(line_text)
        time_str = time.strftime(self._time_format or "[%X]")
        time_text = Text(f"{time_str} ", style="log.time")

        level_text = self.get_level_text(record)

        full_line = Text.assemble(time_text, level_text, message_text)
        self.console.print(full_line)

def reload_logging_config(settings):
    from ofx.settings import RICH_THEME

    branding = settings.app_branding
    logger = logging.getLogger(branding)

    for handler in logger.handlers[:]:
        if handler.name == f"{branding}.console":
            logger.removeHandler(handler)

    console = Console(theme=RICH_THEME)

    log_handler = BeautifiedMetadataHandler(
        console=console,
        rich_tracebacks=settings.debug,
        show_time=False,
        show_level=False,
        markup=True,
        log_time_format="[%X]",
    )
    log_handler.set_name(f"{branding}.console")

    level = logging.DEBUG if settings.debug else logging.INFO
    logger.setLevel(level)
    logger.addHandler(log_handler)

    redact = SecretRedactFilter.get_instance()
    if redact not in logger.filters:
        logger.addFilter(redact)
