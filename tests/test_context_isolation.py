"""Test that RunContext provides proper isolation for flows_dirs."""

from pathlib import Path

from ofx.models.workflow import Workflow
from ofx.runner.core import RunContext
from ofx.runner.workflow import WorkflowRunner


def test_context_has_flows_dirs():
    """Test that RunContext has flows_dirs field."""
    ctx = RunContext()
    assert hasattr(ctx, "flows_dirs")
    assert isinstance(ctx.flows_dirs, list)


def test_context_flows_dirs_initialization():
    """Test that flows_dirs can be initialized with custom paths."""
    custom_path = Path("/custom/path")
    ctx = RunContext(flows_dirs=[custom_path])
    assert custom_path in ctx.flows_dirs


def test_workflow_runner_initializes_flows_dirs():
    """Test that WorkflowRunner initializes flows_dirs if not set."""
    workflow = Workflow(name="test", jobs={})
    ctx = RunContext()

    runner = WorkflowRunner(workflow, ctx)

    assert len(runner.ctx_vars.flows_dirs) > 0
    assert isinstance(runner.ctx_vars.flows_dirs[0], Path)


def test_workflow_runner_preserves_custom_flows_dirs():
    """Test that WorkflowRunner preserves custom flows_dirs."""
    workflow = Workflow(name="test", jobs={})
    custom_path = Path("/custom/workflow/path")
    ctx = RunContext(flows_dirs=[custom_path])

    runner = WorkflowRunner(workflow, ctx)

    assert custom_path in runner.ctx_vars.flows_dirs


def test_add_workflow_dir():
    """Test that add_workflow_dir adds paths to context."""
    workflow = Workflow(name="test", jobs={})
    ctx = RunContext()
    runner = WorkflowRunner(workflow, ctx)

    new_path = Path("/new/workflow/dir")
    initial_count = len(runner.ctx_vars.flows_dirs)

    runner.add_workflow_dir(new_path)

    assert len(runner.ctx_vars.flows_dirs) == initial_count + 1
    assert new_path.absolute() in runner.ctx_vars.flows_dirs


def test_add_workflow_dir_no_duplicates():
    """Test that add_workflow_dir doesn't add duplicates."""
    workflow = Workflow(name="test", jobs={})
    ctx = RunContext()
    runner = WorkflowRunner(workflow, ctx)

    new_path = Path("/unique/path")
    runner.add_workflow_dir(new_path)
    initial_count = len(runner.ctx_vars.flows_dirs)

    # Try adding same path again
    runner.add_workflow_dir(new_path)

    assert len(runner.ctx_vars.flows_dirs) == initial_count


def test_multiple_runners_have_isolated_flows_dirs():
    """Test that multiple WorkflowRunner instances have isolated flows_dirs."""
    workflow1 = Workflow(name="test1", jobs={})
    workflow2 = Workflow(name="test2", jobs={})

    ctx1 = RunContext(flows_dirs=[Path("/path1")])
    ctx2 = RunContext(flows_dirs=[Path("/path2")])

    runner1 = WorkflowRunner(workflow1, ctx1)
    runner2 = WorkflowRunner(workflow2, ctx2)

    # Add path to runner1
    runner1.add_workflow_dir(Path("/custom1"))

    # Verify runner2 is not affected
    assert Path("/custom1").absolute() in runner1.ctx_vars.flows_dirs
    assert Path("/custom1").absolute() not in runner2.ctx_vars.flows_dirs

    # Verify initial paths are preserved
    assert Path("/path1") in runner1.ctx_vars.flows_dirs
    assert Path("/path2") in runner2.ctx_vars.flows_dirs
    assert Path("/path1") not in runner2.ctx_vars.flows_dirs
    assert Path("/path2") not in runner1.ctx_vars.flows_dirs


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
