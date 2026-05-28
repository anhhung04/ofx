"""Tests for shared step handler helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ofx.runner.handlers.shared import (
    build_child_runner,
    resolved_execution_model_kwargs,
)


def test_resolved_execution_model_kwargs_uses_step_runner_defaults(tmp_path) -> None:
    work_dir = (tmp_path / "workspace").resolve()
    step_runner = SimpleNamespace(
        _resolve_shell=lambda: "/bin/sh",
        _resolve_working_dir=lambda: work_dir,
    )

    assert resolved_execution_model_kwargs(step_runner) == {
        "shell": "/bin/sh",
        "working_directory": work_dir,
    }


def test_resolved_execution_model_kwargs_preserves_absolute_paths() -> None:
    step_runner = SimpleNamespace(
        _resolve_shell=lambda: "/bin/zsh",
        _resolve_working_dir=lambda: Path("/opt/ofx"),
    )

    assert resolved_execution_model_kwargs(step_runner)["working_directory"] == Path(
        "/opt/ofx"
    )


def test_build_child_runner_uses_child_context_and_parent() -> None:
    captured: dict[str, object] = {}

    class _Runner:
        def __init__(self, model, ctx, *, parent) -> None:
            captured.update({"model": model, "ctx": ctx, "parent": parent})

    step_runner = SimpleNamespace(
        _child_context=lambda update=None: {"update": update},
    )
    model = object()

    build_child_runner(
        model,
        _Runner,
        step_runner,
        context_update={"workflow_dirs": ["/tmp/wf"]},
    )

    assert captured == {
        "model": model,
        "ctx": {"update": {"workflow_dirs": ["/tmp/wf"]}},
        "parent": step_runner,
    }
