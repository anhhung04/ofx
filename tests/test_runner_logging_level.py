"""Regression tests for StructuredLogger honoring the runner's log_level.

Covers finding M3: ``log_level`` was write-only; records were never filtered
by it. ``StructuredLogger`` must drop records below the runner's effective
level, reading the level per record rather than at construction time.

Note: StructuredLogger prefixes messages with the run context (see
``LogContext.prefix``), so assertions check the trailing message body rather
than exact equality against the bare input.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from ofx.runner import RunContext, Runner
from ofx.runner.logging import StructuredLogger


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def recording_logger():
    logger = logging.getLogger(f"ofx-test-level-{id(object())}")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    handler = _RecordingHandler()
    logger.addHandler(handler)
    return logger, handler


def _make_runner(logger: logging.Logger) -> Runner:
    model = SimpleNamespace(name="job-name", jid="job-1", step_index=None)
    return Runner(model=model, ctx=RunContext(), logger=logger)


def _messages(handler: _RecordingHandler) -> list[str]:
    return [r.getMessage() for r in handler.records]


def _tail(msg: str) -> str:
    """Return the message body after the structured prefix (' | ')."""
    return msg.rsplit(" | ", 1)[-1]


def test_info_dropped_below_runner_log_level(recording_logger):
    logger, handler = recording_logger
    runner = _make_runner(logger)
    assert runner.log_level == logging.DEBUG

    runner.log_level = logging.CRITICAL
    runner._log_info("step info")
    assert _messages(handler) == [], "INFO record must be dropped below CRITICAL"

    runner.log_level = logging.DEBUG
    runner._log_info("visible now")
    assert [_tail(m) for m in _messages(handler)] == ["visible now"]


def test_log_level_is_read_per_record_not_at_construction(recording_logger):
    logger, handler = recording_logger
    runner = _make_runner(logger)
    # Raise the level *after* construction; the next record must be honored.
    runner.log_level = logging.ERROR
    runner._log_info("suppressed")
    runner._log_error("reported")
    assert [_tail(m) for m in _messages(handler)] == ["reported"]


def test_quiet_suppresses_info_but_not_error(recording_logger):
    logger, handler = recording_logger
    runner = _make_runner(logger)
    runner.log_level = logging.ERROR  # api.py quiet=True sets exactly this

    runner._log_info("quiet hides info")
    runner._log_warning("quiet hides warnings")
    runner._log_error("errors still surface")

    assert [_tail(m) for m in _messages(handler)] == ["errors still surface"]


def test_structured_logger_level_filter_applies_directly(recording_logger):
    logger, handler = recording_logger
    runner = _make_runner(logger)
    structured = StructuredLogger(runner, logger=logger)

    structured.info("before")
    runner.log_level = logging.CRITICAL
    structured.info("after")

    assert [_tail(m) for m in _messages(handler)] == ["before"]


def test_warning_and_debug_follow_the_same_threshold(recording_logger):
    logger, handler = recording_logger
    runner = _make_runner(logger)

    runner.log_level = logging.WARNING
    runner._log_debug("debug dropped")
    runner._log_info("info dropped")
    runner._log_warning("warning kept")

    assert [_tail(m) for m in _messages(handler)] == ["warning kept"]


def test_step_runner_critical_suppression(recording_logger):
    """JobExecutor sets step_runner.log_level = CRITICAL; step info is suppressed."""
    logger, handler = recording_logger
    runner = _make_runner(logger)
    runner.log_level = logging.CRITICAL
    runner._log_info("step info must be suppressed")
    assert _messages(handler) == []
