"""Tests for shared step handler helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ofx.runner import RunContext
from ofx.runner.handlers.registry import registry
from ofx.models.step import RunType


def test_create_workflow_runner_uses_parent_dirs_for_search_and_child_context() -> None:
    calls: dict[str, object] = {}
    found_workflow = SimpleNamespace(workflow_path=Path("/tmp/child/workflow.yml"))

    step_runner = SimpleNamespace(
        ctx=RunContext(workflow_dirs=[Path("/tmp/base")]),
        model=SimpleNamespace(uses="child"),
        parent=SimpleNamespace(
            model=SimpleNamespace(
                workflow_path=Path("/tmp/parent/main.yml"),
                defaults=SimpleNamespace(flow_registry_url="https://registry.example"),
            )
        ),
    )

    def _find_workflow(name, search_dirs, registry_url):
        calls["find_workflow"] = (name, search_dirs, registry_url)
        return found_workflow

    class _WorkflowRunner:
        def __init__(self, model, ctx, *, parent):
            calls["workflow_runner"] = (model, ctx, parent)

    with patch("ofx.utils.workflow_utils.find_workflow", _find_workflow), patch(
        "ofx.runner.workflow.WorkflowRunner", _WorkflowRunner
    ):
        result = registry.get(RunType.WORKFLOW)(step_runner)

    assert isinstance(result, _WorkflowRunner)
    assert calls["find_workflow"] == (
        "child",
        (Path("/tmp/base"), Path("/tmp/parent")),
        "https://registry.example",
    )
    assert calls["workflow_runner"] == (
        found_workflow,
        RunContext(
            workflow_dirs=[Path("/tmp/base"), Path("/tmp/parent"), Path("/tmp/child")]
        ),
        step_runner,
    )
