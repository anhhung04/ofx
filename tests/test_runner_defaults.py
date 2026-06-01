"""Tests for shared runner default-resolution helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ofx.models.command import Command
from ofx.models.step import Step
from ofx.runner.run_defaults import (
    model_field_is_explicitly_set,
    resolve_model_run_default,
)
from ofx.settings import DEFAULT_SHELL


def _runner_with_defaults(*, shell: str | None = None, working_directory: Path | None = None):
    run_defaults = SimpleNamespace(
        shell=shell,
        working_directory=working_directory,
    )
    parent = SimpleNamespace(model=SimpleNamespace(defaults=SimpleNamespace(run=run_defaults)))
    return SimpleNamespace(parent=parent)


def test_resolve_model_run_default_reads_nearest_parent_value():
    runner = _runner_with_defaults(shell="/bin/sh")
    model = SimpleNamespace(model_fields_set=set())

    assert resolve_model_run_default(runner, model, "shell", fallback=DEFAULT_SHELL) == "/bin/sh"


def test_resolve_model_run_default_walks_multiple_parents():
    grandparent = SimpleNamespace(
        model=SimpleNamespace(defaults=SimpleNamespace(run=SimpleNamespace(shell="/bin/bash"))),
        parent=None,
    )
    parent = SimpleNamespace(
        model=SimpleNamespace(defaults=SimpleNamespace(run=SimpleNamespace(shell=None))),
        parent=grandparent,
    )
    runner = SimpleNamespace(parent=parent)
    model = SimpleNamespace(model_fields_set=set())

    assert resolve_model_run_default(runner, model, "shell", fallback=DEFAULT_SHELL) == "/bin/bash"


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


def test_resolve_model_run_default_preserves_falsey_parent_value():
    runner = SimpleNamespace(
        parent=SimpleNamespace(
            model=SimpleNamespace(
                defaults=SimpleNamespace(run=SimpleNamespace(retries=0))
            )
        )
    )
    model = SimpleNamespace(model_fields_set=set())

    assert resolve_model_run_default(runner, model, "retries", fallback=3) == 0


def test_resolve_model_run_default_prefers_explicit_shell_value():
    runner = _runner_with_defaults(shell="/bin/sh")
    model = Step(run="echo hi", shell="/bin/zsh")

    assert (
        resolve_model_run_default(
            runner,
            model,
            "shell",
            fallback=DEFAULT_SHELL,
        )
        == "/bin/zsh"
    )


def test_resolve_model_run_default_falls_back_to_parent_then_default_for_shell():
    assert (
        resolve_model_run_default(
            _runner_with_defaults(shell="/bin/sh"),
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


def test_resolve_model_run_default_prefers_explicit_working_directory():
    runner = _runner_with_defaults(working_directory=Path("/tmp"))
    model = Command(cmd="echo hi", working_directory=Path("/opt"))

    assert resolve_model_run_default(
        runner,
        model,
        "working_directory",
        fallback=Path.cwd(),
    ) == Path("/opt")


def test_resolve_model_run_default_falls_back_to_parent_then_cwd_for_working_directory():
    assert resolve_model_run_default(
        _runner_with_defaults(working_directory=Path("/tmp")),
        Command(cmd="echo hi"),
        "working_directory",
        fallback=Path.cwd(),
    ) == Path("/tmp")
    assert resolve_model_run_default(
        SimpleNamespace(parent=None),
        Command(cmd="echo hi"),
        "working_directory",
        fallback=Path.cwd(),
    ) == Path.cwd()
