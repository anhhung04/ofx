"""Tests for task executor command-runner helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ofx.runner import RunContext
from ofx.runner.executors.task import TaskExecutor


@pytest.mark.asyncio
async def test_auto_install_tool_uses_isolated_env_context(monkeypatch):
    captured_envs = []
    logs: list[str] = []

    class _FakeCommandRunner:
        def __init__(self, command_model, ctx):
            self.command_model = command_model
            self.ctx = ctx

        async def run(self):
            self.ctx.envs["MUTATED_BY"] = self.command_model.cmd
            captured_envs.append(dict(self.ctx.envs))
            return SimpleNamespace(
                status=SimpleNamespace(value="completed"),
                outputs={"exit_code": 0},
                error=None,
            )

    monkeypatch.setattr(
        "ofx.runner.executors.task.CommandRunner",
        _FakeCommandRunner,
    )
    monkeypatch.setattr("shutil.which", lambda _tool: "/usr/bin/fake-tool")

    runner = SimpleNamespace(
        ctx=RunContext(envs={"BASE": "1"}),
        _log_info=logs.append,
        _log_warning=logs.append,
    )

    await TaskExecutor()._auto_install_tool(runner, "fake-tool", "install fake-tool")

    assert runner.ctx.envs["BASE"] == "1"
    assert "MUTATED_BY" not in runner.ctx.envs
    assert len(captured_envs) == 1
    assert captured_envs[0]["BASE"] == "1"
    assert captured_envs[0]["MUTATED_BY"] == "install fake-tool"
    assert logs == [
        "Tool 'fake-tool' not found - auto-installing with: install fake-tool",
        "Tool 'fake-tool' installed successfully",
    ]
