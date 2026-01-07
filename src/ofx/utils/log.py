import logging


def reload_logging_config(settings):
    """Reloads the logging configuration based on the current settings"""
    from rich.console import Console
    from rich.logging import RichHandler
    from ofx.settings import RICH_THEME

    branding = settings.app_branding
    pre_logger = logging.getLogger(branding)
    for handler in logging.getLogger(branding).handlers:
        if handler.name == f"{branding}.console":
            pre_logger.removeHandler(handler)

    themed_console = Console(theme=RICH_THEME)

    log_handler = RichHandler(
        console=themed_console,
        rich_tracebacks=settings.debug,
        show_time=True,
        show_level=True,
        show_path=settings.debug,
        log_time_format="[%X]",
    )
    log_handler.set_name(f"{branding}.console")

    if settings.debug:
        pre_logger.setLevel(logging.DEBUG)
        log_handler.setLevel(logging.DEBUG)
    else:
        log_handler.setLevel(logging.INFO)
        pre_logger.setLevel(logging.INFO)
    
    pre_logger.addHandler(log_handler)
