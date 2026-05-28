"""Tests for step handler registry behavior."""

from __future__ import annotations

from ofx.models.step import RunType
from ofx.runner.handlers.registry import HandlerRegistry


def test_register_supports_multiple_run_types() -> None:
    registry = HandlerRegistry()
    calls: list[str] = []

    @registry.register(RunType.SCRIPT, RunType.SCRIPT_FILE)
    def handler(step_runner):
        calls.append(step_runner)
        return "runner"

    assert registry.get(RunType.SCRIPT) is handler
    assert registry.get(RunType.SCRIPT_FILE) is handler
    assert registry.create_runner(RunType.SCRIPT_FILE, "step-runner") == "runner"
    assert calls == ["step-runner"]
