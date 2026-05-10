import logging

from ofx.runner.logging import get_logger
from ofx.settings import settings


def test_shared_logger_singleton():
    logger1 = get_logger()
    logger2 = get_logger()
    assert isinstance(logger1, logging.Logger)
    assert logger1 is logger2
    # The logger name should match the branding
    assert logger1.name == settings.app_branding
