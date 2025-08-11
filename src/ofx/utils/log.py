import logging


def reload_logging_config(settings):
    """
    Reloads the logging configuration based on the current settings.
    This is useful if settings are changed at runtime.
    """
    for handler in logging.getLogger("ofx").handlers:
        if handler.name == "console" or handler.name == "ofx.notification":
            logging.getLogger("ofx").removeHandler(handler)

    if settings.grepable:
        log_handler = logging.StreamHandler()
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        log_handler.setFormatter(formatter)
    else:
        from rich.logging import RichHandler

        log_handler = RichHandler(
            rich_tracebacks=True,
            show_time=True,
            show_level=True,
            show_path=settings.debug,
        )

    log_handler.set_name("console")
    logger = logging.getLogger("ofx")

    if settings.debug:
        log_handler.setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
        log_handler.setLevel(logging.INFO)

    logger.addHandler(log_handler)
    logger.propagate = False
