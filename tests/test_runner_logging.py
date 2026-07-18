"""Tests for shared runner log formatting helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from ofx.models.step import Step
from ofx.models.workflow import Workflow
from ofx.runner.logging import (
    LogContext,
    StructuredLogger,
    bubble_context_log,
)
from ofx.runner.runner import Runner
from ofx.runner.step import StepRunner
from ofx.runner.tasks.runner import TaskExecution, TaskRunner
from ofx.runner.tool_installer import ToolInstallation, ToolInstallerRunner
from ofx.runner.workflow import WorkflowRunner


class ParentStub:
    def __init__(self) -> None:
        self.received: str | None = None

    def _produce_log(self, message: str) -> str:
        self.received = message
        return f"parent::{message}"


def test_bubble_context_log_formats_and_bubbles_message():
    parent = ParentStub()

    result = bubble_context_log(parent, "hello", model_name="wf", model_jid="scan")

    assert parent.received == "name=wf | job=scan › hello"
    assert result == "parent::name=wf | job=scan › hello"

def test_log_context_prefix_rendering_uses_all_present_fields():
    context = LogContext(
        run_id="run-1",
        runner_type="WorkflowRunner",
        model_name="wf",
        model_jid="scan",
        step_index=2,
        status="completed",
    )

    assert context.prefix == "WorkflowRunner | name=wf | job=scan | step=2 | status=completed"


def test_structured_logger_uses_shared_log_dispatch():
    calls: list[tuple[str, str, dict]] = []

    class _Logger:
        def debug(self, message, *, extra):
            calls.append(("debug", message, extra))

    runner = SimpleNamespace(
        run_id="run-1",
        status=SimpleNamespace(value="completed"),
        model=SimpleNamespace(name="wf", jid="scan", step_index=None),
        parent=None,
        name="runner-name",
    )
    logger = StructuredLogger(runner, logger=_Logger())

    logger.debug("hello")

    assert calls[0][0] == "debug"
    assert calls[0][1].endswith("hello")
    assert "log_context" in calls[0][2]
    assert calls[0][2]["log_context"]["run_id"] == "run-1"


def test_structured_logger_derives_context_once_per_log_call():
    calls: list[tuple[str, dict]] = []

    class _Logger:
        def info(self, message, *, extra):
            calls.append((message, extra))

    runner = SimpleNamespace()
    context = LogContext(run_id="run-1", runner_type="WorkflowRunner")

    with patch(
        "ofx.runner.logging.LogContext.from_runner",
        return_value=context,
    ) as mock_from_runner:
        StructuredLogger(runner, logger=_Logger()).info("hello")

    mock_from_runner.assert_called_once_with(runner)
    assert calls == [
        (
            "WorkflowRunner | hello",
            {"log_context": context.__dict__},
        )
    ]


def test_structured_logger_format_message_reuses_optional_context():
    runner = SimpleNamespace()
    logger = StructuredLogger(runner, logger=SimpleNamespace())
    context = LogContext(run_id="run-1", runner_type="WorkflowRunner")

    with patch(
        "ofx.runner.logging.LogContext.from_runner",
        side_effect=AssertionError("should not derive context"),
    ):
        assert logger.format_message("hello", context) == "WorkflowRunner | hello"


def test_base_runner_produce_log_uses_structured_logger_formatting():
    runner = object.__new__(Runner)
    runner._structured_logger = StructuredLogger(SimpleNamespace(), logger=SimpleNamespace())

    with patch.object(
        runner._structured_logger,
        "format_message",
        return_value="formatted::hello",
    ) as mock_format:
        assert runner._produce_log("hello") == "formatted::hello"

    mock_format.assert_called_once_with("hello")


def test_workflow_runner_uses_shared_context_log_formatting():
    runner = object.__new__(WorkflowRunner)
    runner.parent = ParentStub()
    runner.model = Workflow(name="recon", jobs={"scan": {"steps": [{"run": "echo hi"}]}})

    assert runner._produce_log("start") == "parent::name=recon › start"


def test_step_runner_uses_shared_context_log_formatting():
    runner = object.__new__(StepRunner)
    runner.parent = ParentStub()
    runner.model = Step(step_index=3, run="echo hi")

    assert runner._produce_log("done") == "parent::step=3 › done"


def test_task_runner_uses_prefixed_log_formatting():
    runner = object.__new__(TaskRunner)
    runner.model = TaskExecution(task_name="scan")

    assert runner._produce_log("done") == "[Task:scan] done"


def test_tool_installer_runner_uses_prefixed_log_formatting():
    runner = object.__new__(ToolInstallerRunner)
    runner.model = ToolInstallation()

    assert runner._produce_log("done") == "[ToolInstaller] done"
