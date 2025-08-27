import logging


def reload_logging_config(settings):
    """
    Reloads the logging configuration based on the current settings.
    This is useful if settings are changed at runtime.
    """
    pre_logger = logging.getLogger(settings.app_branding)
    for handler in logging.getLogger(settings.app_branding).handlers:
        if handler.name == "ofx.console" or handler.name == "ofx.notification":
            pre_logger.removeHandler(handler)

    log_handler = None
    if settings.grepable:
        log_handler = logging.StreamHandler()
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        log_handler.setFormatter(formatter)
    else:
        from rich.logging import RichHandler

        log_handler = RichHandler(
            rich_tracebacks=settings.debug,
            show_time=True,
            show_level=True,
            show_path=settings.debug,
            log_time_format="[%X]",
        )
    log_handler.set_name("ofx.console")

    if settings.debug:
        pre_logger.setLevel(logging.DEBUG)
        log_handler.setLevel(logging.DEBUG)
    else:
        log_handler.setLevel(logging.INFO)
        pre_logger.setLevel(logging.INFO)
    pre_logger.addHandler(log_handler)
