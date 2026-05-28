"""Tests for shared runner default-resolution helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ofx.models.command import Command
from ofx.models.step import Step
from ofx.runner.run_defaults import (
    model_field_is_explicitly_set,
    resolve_model_run_default,
    resolve_model_shell,
    resolve_model_working_directory,
    resolve_parent_run_default,
)
from ofx.settings import DEFAULT_SHELL


def _runner_with_defaults(*, shell: str | None = None, working_directory: Path | None = None):
    run_defaults = SimpleNamespace(
        shell=shell,
        working_directory=working_directory,
    )
    parent = SimpleNamespace(model=SimpleNamespace(defaults=SimpleNamespace(run=run_defaults)))
    return SimpleNamespace(parent=parent)


def test_resolve_parent_run_default_reads_nearest_parent_value():
    runner = _runner_with_defaults(shell="/bin/sh")

    assert resolve_parent_run_default(runner, "shell") == "/bin/sh"


def test_model_field_is_explicitly_set_reflects_pydantic_fields_set():
    model = Step(run="echo hi", **{"working-directory": "nested"})

    assert model_field_is_explicitly_set(model, "working_directory") is True
    assert model_field_is_explicitly_set(model, "shell") is False


def test_resolve_model_run_default_prefers_explicit_then_parent_then_fallback():
    explicit_model = Step(run="echo hi", shell="/bin/zsh")
    inherited_runner = _runner_with_defaults(shell="/bin/sh")

    assert (
        resolve_model_run_default(
            inherited_runner,
            explicit_model,
            "shell",
            fallback=DEFAULT_SHELL,
        )
        == "/bin/zsh"
    )
    assert (
        resolve_model_run_default(
            inherited_runner,
            Step(run="echo hi"),
            "shell",
            fallback=DEFAULT_SHELL,
        )
        == "/bin/sh"
    )
    assert (
        resolve_model_run_default(
            SimpleNamespace(parent=None),
            Step(run="echo hi"),
            "shell",
            fallback=DEFAULT_SHELL,
        )
        == DEFAULT_SHELL
    )


def test_resolve_model_shell_prefers_explicit_model_value():
    runner = _runner_with_defaults(shell="/bin/sh")
    model = Step(run="echo hi", shell="/bin/zsh")

    assert resolve_model_shell(runner, model) == "/bin/zsh"


def test_resolve_model_shell_falls_back_to_parent_then_default():
    assert resolve_model_shell(_runner_with_defaults(shell="/bin/sh"), Step(run="echo hi")) == "/bin/sh"
    assert resolve_model_shell(SimpleNamespace(parent=None), Step(run="echo hi")) == DEFAULT_SHELL


def test_resolve_model_working_directory_prefers_explicit_model_value():
    runner = _runner_with_defaults(working_directory=Path("/tmp"))
    model = Command(cmd="echo hi", working_directory=Path("/opt"))

    assert resolve_model_working_directory(runner, model) == Path("/opt")


def test_resolve_model_working_directory_falls_back_to_parent_then_cwd():
    assert resolve_model_working_directory(
        _runner_with_defaults(working_directory=Path("/tmp")),
        Command(cmd="echo hi"),
    ) == Path("/tmp")
    assert resolve_model_working_directory(SimpleNamespace(parent=None), Command(cmd="echo hi")) == Path.cwd()
