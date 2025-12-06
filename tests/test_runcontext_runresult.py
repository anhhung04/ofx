"""
Test RunContext and RunResult correctness and optimization opportunities.
"""

import asyncio
from pathlib import Path
from typing import AsyncGenerator

import pytest

from ofx.models import DefaultRunner
from ofx.runner.base import BaseRunner
from ofx.runner.core import RunContext, RunnerStatus, RunResult


class TestRunContext:
    """Test RunContext functionality."""

    def test_runcontext_defaults(self):
        """Test that RunContext has sensible defaults."""
        ctx = RunContext()

        assert ctx.inputs == {}
        assert ctx.secrets == {}
        assert ctx.envs == {}
        assert ctx.output_path == Path.cwd() / "out"
        assert ctx.vars == {}
        assert ctx.flows_dirs == []

    def test_runcontext_initialization(self):
        """Test RunContext initialization with values."""
        ctx = RunContext(
            inputs={"key": "value"},
            secrets={"api": "secret"},
            envs={"PATH": "/usr/bin"},
            output_path=Path("/tmp"),
            vars={"step1": "result1"},
            flows_dirs=[Path("/flows")],
        )

        assert ctx.inputs["key"] == "value"
        assert ctx.secrets["api"] == "secret"
        assert ctx.envs["PATH"] == "/usr/bin"
        assert ctx.output_path == Path("/tmp")
        assert ctx.vars["step1"] == "result1"
        assert len(ctx.flows_dirs) == 1

    def test_runcontext_mutability(self):
        """Test that RunContext allows mutations."""
        ctx = RunContext()

        # Should allow updates
        ctx.inputs["new"] = "value"
        ctx.secrets["token"] = "secret"
        ctx.envs["VAR"] = "val"
        ctx.vars["result"] = "output"
        ctx.flows_dirs.append(Path("/new"))

        assert ctx.inputs["new"] == "value"
        assert ctx.secrets["token"] == "secret"
        assert ctx.envs["VAR"] == "val"
        assert ctx.vars["result"] == "output"
        assert Path("/new") in ctx.flows_dirs

    def test_runcontext_extra_fields(self):
        """Test that RunContext allows extra fields."""
        ctx = RunContext(custom_field="custom_value")

        # extra="allow" should permit this
        assert ctx.custom_field == "custom_value"

    def test_copy_for_child_deep_merge(self):
        """Test copy_for_child merges dictionaries correctly."""
        parent = RunContext(
            inputs={"a": 1, "b": 2}, secrets={"x": "y"}, envs={"E1": "v1", "E2": "v2"}
        )

        child = parent.copy_for_child(
            inputs={"b": 3, "c": 4},  # Override b, add c
            secrets={"z": "w"},  # Add z
            envs={"E2": "v2_new"},  # Override E2
        )

        # Parent should have original values
        assert parent.inputs == {"a": 1, "b": 2}
        assert parent.secrets == {"x": "y"}
        assert parent.envs == {"E1": "v1", "E2": "v2"}

        # Child should have merged values
        assert child.inputs == {"a": 1, "b": 3, "c": 4}
        assert child.secrets == {"x": "y", "z": "w"}
        assert child.envs == {"E1": "v1", "E2": "v2_new"}


class TestRunResult:
    """Test RunResult functionality."""

    def test_runresult_initialization(self):
        """Test RunResult initialization."""
        result = RunResult(
            status=RunnerStatus.COMPLETED, name="test", run_id="test-123"
        )

        assert result.status == RunnerStatus.COMPLETED
        assert result.error is None
        assert result.outputs == {}
        assert result.name == "test"
        assert result.run_id == "test-123"
        assert result.metadata == {}

    def test_runresult_with_error(self):
        """Test RunResult with error."""
        result = RunResult(
            status=RunnerStatus.FAILED,
            error="Test error",
            name="test",
            run_id="test-123",
        )

        assert result.status == RunnerStatus.FAILED
        assert result.error == "Test error"

    def test_runresult_with_outputs(self):
        """Test RunResult with outputs."""
        result = RunResult(
            status=RunnerStatus.COMPLETED,
            outputs={"key": "value", "nested": {"a": 1}},
            name="test",
            run_id="test-123",
        )

        assert result.outputs["key"] == "value"
        assert result.outputs["nested"]["a"] == 1

    def test_runresult_mutability(self):
        """Test that RunResult allows mutations."""
        result = RunResult(status=RunnerStatus.RUNNING, name="test", run_id="test-123")

        # Should allow status updates
        result.status = RunnerStatus.COMPLETED
        result.error = "Some error"
        result.outputs["new"] = "output"
        result.metadata["duration"] = 10

        assert result.status == RunnerStatus.COMPLETED
        assert result.error == "Some error"
        assert result.outputs["new"] == "output"
        assert result.metadata["duration"] == 10


class MockRunner(BaseRunner):
    """Mock runner for testing."""

    def __init__(self, ctx: RunContext, do_run_type="normal"):
        super().__init__("MockRunner", ctx)
        self.do_run_type = do_run_type
        self.pre_run_called = False
        self.post_run_called = False
        self.do_run_iterations = 0

    async def _do_run(self):
        if self.do_run_type == "generator":
            # Return async generator
            async def gen():
                for i in range(3):
                    self.do_run_iterations += 1
                    yield i

            return gen()
        elif self.do_run_type == "error":
            raise RuntimeError("Test error")
        else:
            # Normal execution
            await asyncio.sleep(0.01)

    async def _pre_run(self):
        self.pre_run_called = True

    async def _post_run(self):
        self.post_run_called = True

    def _produce_log(self, message):
        return f"[MockRunner] {message}"


class TestRunnerExecutionFlow:
    """Test the run() method execution flow."""

    @pytest.mark.asyncio
    async def test_normal_execution_flow(self):
        """Test normal execution without errors."""
        ctx = RunContext()
        runner = MockRunner(ctx)

        result = await runner.run()

        assert runner.pre_run_called
        assert runner.post_run_called
        assert result.status == RunnerStatus.COMPLETED
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execution_with_error(self):
        """Test execution with error in _do_run."""
        ctx = RunContext()
        runner = MockRunner(ctx, do_run_type="error")

        result = await runner.run()

        assert runner.pre_run_called
        assert runner.post_run_called
        assert result.status == RunnerStatus.FAILED
        # Error now includes exception type
        assert result.error is not None
        assert "RuntimeError" in result.error
        assert "Test error" in result.error

    @pytest.mark.asyncio
    async def test_result_updates_correctly(self):
        """Test that get_result() returns updated result."""
        ctx = RunContext()
        runner = MockRunner(ctx)

        # Before run
        result_before = runner.get_result()
        assert result_before.status == RunnerStatus.IDLE

        # After run
        result_after = await runner.run()
        assert result_after.status == RunnerStatus.COMPLETED
        assert result_after.run_id == runner.run_id

    @pytest.mark.asyncio
    async def test_context_vars_preserved(self):
        """Test that context vars are preserved."""
        ctx = RunContext(inputs={"key": "value"}, secrets={"token": "secret"})
        runner = MockRunner(ctx)

        await runner.run()

        # Context should be preserved
        assert runner.ctx_vars.inputs["key"] == "value"
        assert runner.ctx_vars.secrets["token"] == "secret"

    @pytest.mark.asyncio
    async def test_hooks_called_correctly(self):
        """Test that hooks are called at the right time."""
        ctx = RunContext()
        hook_calls = []

        def on_start(runner):
            hook_calls.append("on_start")

        def on_end(runner):
            hook_calls.append("on_end")

        runner = MockRunner(ctx)
        runner._hooks["on_start"] = on_start
        runner._hooks["on_end"] = on_end

        await runner.run()

        assert hook_calls == ["on_start", "on_end"]


class TestRunnerStatusTransitions:
    """Test status transitions during execution."""

    @pytest.mark.asyncio
    async def test_status_idle_to_running_to_completed(self):
        """Test status transitions for successful run."""
        ctx = RunContext()
        runner = MockRunner(ctx)

        assert runner.status == RunnerStatus.IDLE

        # Start run (don't await to check intermediate state)
        run_task = asyncio.create_task(runner.run())
        await asyncio.sleep(0.001)  # Let it start

        # Status should be RUNNING or COMPLETED
        assert runner.status in [RunnerStatus.RUNNING, RunnerStatus.COMPLETED]

        # Wait for completion
        result = await run_task
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_status_transitions_on_error(self):
        """Test status transitions when error occurs."""
        ctx = RunContext()
        runner = MockRunner(ctx, do_run_type="error")

        result = await runner.run()

        assert result.status == RunnerStatus.FAILED
        assert runner.status == RunnerStatus.FAILED


class TestEdgeCases:
    """Test edge cases and potential issues."""

    @pytest.mark.asyncio
    async def test_empty_context(self):
        """Test runner with empty context."""
        ctx = RunContext()
        runner = MockRunner(ctx)

        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_post_run_error_handling(self):
        """Test that post_run errors are caught."""
        ctx = RunContext()
        runner = MockRunner(ctx)

        # Make post_run raise an error
        async def bad_post_run():
            raise RuntimeError("Post-run error")

        runner._post_run = bad_post_run

        result = await runner.run()

        # Should mark as FAILED
        assert result.status == RunnerStatus.FAILED
        # Error should contain post-run error details
        assert result.error is not None
        assert "Post-run error" in result.error

    @pytest.mark.asyncio
    async def test_multiple_runs(self):
        """Test running the same runner multiple times."""
        ctx = RunContext()
        runner = MockRunner(ctx)

        result1 = await runner.run()
        result2 = await runner.run()

        # Both should complete
        assert result1.status == RunnerStatus.COMPLETED
        assert result2.status == RunnerStatus.COMPLETED


class TestTimingMetadata:
    """Test timing metadata in results."""

    @pytest.mark.asyncio
    async def test_result_has_timing(self):
        """Test that result includes timing metadata."""
        ctx = RunContext()
        runner = MockRunner(ctx)

        result = await runner.run()

        # Should have timing metadata
        assert "start_time" in result.metadata
        assert "end_time" in result.metadata
        assert "duration" in result.metadata

        # Duration should be positive
        assert result.metadata["duration"] > 0

        # end_time should be after start_time
        assert result.metadata["end_time"] > result.metadata["start_time"]

    @pytest.mark.asyncio
    async def test_set_timing_manual(self):
        """Test manual timing setting."""
        result = RunResult(
            status=RunnerStatus.COMPLETED, name="test", run_id="test-123"
        )

        start = 1000.0
        end = 1010.5
        result.set_timing(start, end)

        assert result.metadata["start_time"] == start
        assert result.metadata["end_time"] == end
        assert result.metadata["duration"] == 10.5

    @pytest.mark.asyncio
    async def test_set_timing_auto_end(self):
        """Test timing with automatic end time."""
        import time

        result = RunResult(
            status=RunnerStatus.COMPLETED, name="test", run_id="test-123"
        )

        start = time.time()
        result.set_timing(start)  # end_time defaults to now

        assert "end_time" in result.metadata
        assert result.metadata["end_time"] >= start


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
