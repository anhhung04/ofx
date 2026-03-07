import logging

from ofx.settings import settings
from ofx.utils.log import reload_logging_config

_logger: logging.Logger | None = None


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
