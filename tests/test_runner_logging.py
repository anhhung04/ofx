"""Tests for shared runner log formatting helpers."""

from __future__ import annotations

from ofx.models.step import Step
from ofx.models.workflow import Workflow
from ofx.runner.logging import bubble_context_log, bubble_tagged_log, prefix_log
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


def test_bubble_tagged_log_formats_prefix_and_tags():
    parent = ParentStub()

    result = bubble_tagged_log(parent, "hello", prefix="job=scan", tags=("cloud",))

    assert parent.received == "job=scan [cloud] › hello"
    assert result == "parent::job=scan [cloud] › hello"


def test_prefix_log_formats_prefix_and_message():
    assert prefix_log("hello", "[Task:scan]") == "[Task:scan] hello"


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
