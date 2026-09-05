"""Tests for workflow directory operations and context isolation"""

from pathlib import Path

import pytest
import yaml

from ofx.runner import RunContext, WorkflowRunner
from ofx.utils.workflow_utils import (
    find_workflow,
    workflow_dirs_with_path,
)

class _ReusableWorkflowParentStub:
    """Minimal parent surface for reused workflow runner tests."""

    parent = None
    run_id = "parent-run"

    def _namespace(self) -> str:
        return "ParentRunner:stub"

    def _produce_log(self, message):
        return str(message)

class TestWorkflowDirectoryOperations:
    """Test workflow directory management and isolation"""

    def test_workflow_dirs_with_path_adds_new_path(self):
        """Test that workflow_dirs_with_path adds a new path to the copy"""
        workflow_dirs = [Path("/existing/path")]
        new_path = Path("/new/path")

        result = workflow_dirs_with_path(workflow_dirs, new_path)

        assert new_path.absolute() in result
        assert len(result) == 2
        assert workflow_dirs == [Path("/existing/path")]

    def test_workflow_dirs_with_path_ignores_duplicate(self):
        """Test that workflow_dirs_with_path doesn't add duplicates"""
        existing_path = Path("/existing/path").absolute()
        workflow_dirs = [existing_path]

        result = workflow_dirs_with_path(workflow_dirs, existing_path)

        assert len(result) == 1
        assert result[0] == existing_path

    def test_workflow_dirs_with_path_converts_string_to_path(self):
        """Test that workflow_dirs_with_path accepts string paths"""
        workflow_dirs = []
        string_path = "/some/path"

        result = workflow_dirs_with_path(workflow_dirs, string_path)

        assert Path(string_path).absolute() in result

    def test_workflow_dirs_with_path_returns_updated_copy(self):
        original = [Path("/existing/path").absolute()]

        result = workflow_dirs_with_path(original, "/new/path")

        assert result is not original
        assert original == [Path("/existing/path").absolute()]
        assert Path("/new/path").absolute() in result

    def test_context_has_default_workflow_dirs(self):
        """Test that RunContext initializes with default workflow_dirs"""
        from ofx.settings import get_workflow_search_dirs

        ctx = RunContext()

        assert isinstance(ctx.workflow_dirs, list)
        assert ctx.workflow_dirs == get_workflow_search_dirs()

    def test_workflow_runner_initializes_workflow_dirs(self):
        """Test that WorkflowRunner uses default workflow_dirs from context"""
        from ofx.settings import get_workflow_search_dirs

        test_workflow_content = """
name: test
defaults:
  workflows_base_dir: .
jobs:
  test:
    name: Test Job
    steps:
      - name: Test step
        run: echo "test"
"""
        workflow = yaml.safe_load(test_workflow_content)
        from ofx.models.workflow import Workflow

        workflow_obj = Workflow.model_validate(workflow)

        ctx = RunContext()
        expected_dirs = get_workflow_search_dirs()
        assert ctx.workflow_dirs == expected_dirs

        runner = WorkflowRunner(workflow_obj, ctx)

        assert runner.ctx.workflow_dirs == expected_dirs

    def test_workflow_runner_preserves_existing_dirs(self):
        """Test that WorkflowRunner preserves workflow_dirs if already set"""
        test_workflow_content = """
name: test
defaults:
  workflows_base_dir: .
jobs:
  test:
    name: Test Job
    steps:
      - name: Test step
        run: echo "test"
"""
        workflow = yaml.safe_load(test_workflow_content)
        from ofx.models.workflow import Workflow

        workflow_obj = Workflow.model_validate(workflow)

        custom_dir = Path("/custom/dir").absolute()
        ctx = RunContext(workflow_dirs=[custom_dir])

        runner = WorkflowRunner(workflow_obj, ctx)

        assert custom_dir in runner.ctx.workflow_dirs

    def test_workflow_runner_root_name_and_reuse_helpers(self):
        test_workflow_content = """
name: test
defaults:
  workflows_base_dir: .
jobs:
  test:
    steps:
      - run: echo test
"""
        workflow = yaml.safe_load(test_workflow_content)
        from ofx.models.workflow import Workflow

        workflow_obj = Workflow.model_validate(workflow)

        root_runner = WorkflowRunner(workflow_obj, RunContext())
        reused_runner = WorkflowRunner(
            workflow_obj,
            RunContext(),
            parent=_ReusableWorkflowParentStub(),
        )

        assert root_runner._is_reused is False
        assert root_runner.name.startswith(f"[RUN-{root_runner.run_id}]:")
        assert reused_runner._is_reused is True

    def test_workflow_runner_exposes_registered_child_runners(self):
        test_workflow_content = """
name: test
defaults:
  workflows_base_dir: .
jobs:
  test:
    steps:
      - run: echo test
"""
        workflow = yaml.safe_load(test_workflow_content)
        from ofx.models.workflow import Workflow

        workflow_obj = Workflow.model_validate(workflow)
        runner = WorkflowRunner(workflow_obj, RunContext())
        child_runner = WorkflowRunner(
            workflow_obj,
            RunContext(),
            parent=_ReusableWorkflowParentStub(),
        )
        runner._runners = {"ok": child_runner}

        assert runner.runners == {"ok": child_runner}

    @pytest.mark.asyncio
    async def test_context_isolation_between_runners(self):
        """Test that different runners have isolated contexts"""
        test_workflow_content = """
name: test
defaults:
  workflows_base_dir: .
jobs:
  test:
    name: Test Job
    steps:
      - name: Test step
        run: echo "test"
"""
        workflow = yaml.safe_load(test_workflow_content)
        from ofx.models.workflow import Workflow

        workflow_obj = Workflow.model_validate(workflow)

        ctx1 = RunContext(workflow_dirs=[Path("/dir1").absolute()])
        ctx2 = RunContext(workflow_dirs=[Path("/dir2").absolute()])

        runner1 = WorkflowRunner(workflow_obj, ctx1)
        runner2 = WorkflowRunner(workflow_obj, ctx2)

        assert Path("/dir1").absolute() in runner1.ctx.workflow_dirs
        assert Path("/dir1").absolute() not in runner2.ctx.workflow_dirs

        assert Path("/dir2").absolute() in runner2.ctx.workflow_dirs
        assert Path("/dir2").absolute() not in runner1.ctx.workflow_dirs

    def test_find_workflow_with_file_path(self, tmp_path):
        """Test finding workflow from absolute file path"""
        workflow_content = """
name: test_workflow
defaults:
  workflows_base_dir: .
jobs:
  test:
    name: Test Job
    steps:
      - name: Test step
        run: echo "test"
"""
        workflow_file = tmp_path / "test.yml"
        workflow_file.write_text(workflow_content)

        workflow_dirs = [tmp_path]
        workflow = find_workflow(str(workflow_file), tuple(workflow_dirs))

        assert workflow.name == "test_workflow"
        assert workflow.workflow_path.exists()
        assert workflow.workflow_path == workflow_file

    def test_find_workflow_with_name(self, tmp_path):
        """Test finding workflow by name from directory"""
        workflow_content = """
name: named_workflow
defaults:
  workflows_base_dir: .
jobs:
  test:
    name: Test Job
    steps:
      - name: Test step
        run: echo "test"
"""
        workflow_file = tmp_path / "myworkflow.yml"
        workflow_file.write_text(workflow_content)

        workflow_dirs = [tmp_path]
        workflow = find_workflow("myworkflow", tuple(workflow_dirs))

        assert workflow.name == "named_workflow"
        assert workflow.workflow_path.exists()
        assert workflow.workflow_path.name == "myworkflow.yml"

    def test_find_workflow_with_invalid_yaml_reports_path(self, tmp_path):
        workflow_file = tmp_path / "broken.yml"
        workflow_file.write_text("name: [unterminated\n")

        with pytest.raises(RuntimeError, match="Invalid YAML in workflow file"):
            find_workflow(str(workflow_file), (tmp_path,))

    def test_find_workflow_with_invalid_remote_yaml_reports_source(self, monkeypatch):
        class _Response:
            text = "name: [unterminated\n"

            def raise_for_status(self):
                return None

        monkeypatch.setattr("ofx.utils.workflow_utils.is_remote_path", lambda path: True)
        monkeypatch.setattr("ofx.utils.workflow_utils.is_git_repo", lambda path: False)
        monkeypatch.setattr("ofx.utils.workflow_utils.httpx.get", lambda url, timeout=30: _Response())

        with pytest.raises(RuntimeError, match="Invalid YAML in remote workflow https://example.com/test.yml"):
            find_workflow("https://example.com/test.yml", tuple())

    def test_find_workflow_with_invalid_cloned_yaml_reports_action_path(self, monkeypatch, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "action.yml").write_text("name: [unterminated\n")

        monkeypatch.setattr("ofx.utils.workflow_utils.clone_remote_repo", lambda workflow_name, flow_registry_url: repo_dir)

        with pytest.raises(RuntimeError, match=r"Invalid YAML in workflow file .*action.yml"):
            find_workflow("org/repo", tuple())

    def test_find_workflow_caching(self, tmp_path):
        """Test that find_workflow uses LRU cache"""
        workflow_content = """
name: cached_workflow
defaults:
  workflows_base_dir: .
jobs:
  test:
    name: Test Job
    steps:
      - name: Test step
        run: echo "test"
"""
        workflow_file = tmp_path / "cached.yml"
        workflow_file.write_text(workflow_content)

        workflow_dirs = (tmp_path,)

        workflow1 = find_workflow(str(workflow_file), workflow_dirs)
        workflow2 = find_workflow(str(workflow_file), workflow_dirs)

        assert workflow1 is not workflow2
        assert workflow1.name == workflow2.name
        assert workflow1.workflow_path == workflow2.workflow_path

    def test_find_workflow_different_dirs_different_cache(self, tmp_path):
        """Test that different search dirs create different cache entries"""
        workflow_content = """
name: multi_dir_workflow
defaults:
  workflows_base_dir: .
jobs:
  test:
    name: Test Job
    steps:
      - name: Test step
        run: echo "test"
"""
        workflow_file = tmp_path / "multi.yml"
        workflow_file.write_text(workflow_content)

        dirs1 = (tmp_path,)
        dirs2 = (tmp_path, Path.cwd())

        workflow1 = find_workflow(str(workflow_file), dirs1)
        workflow2 = find_workflow(str(workflow_file), dirs2)

        assert workflow1.name == workflow2.name
        assert workflow1.workflow_path == workflow2.workflow_path

    @pytest.mark.asyncio
    async def test_workflow_dirs_updated_during_execution(self, tmp_path):
        """Test that workflow_dirs are updated when workflow is resolved"""
        subworkflow_dir = tmp_path / "subflows"
        subworkflow_dir.mkdir()

        workflow_content = f"""
name: parent_workflow
defaults:
  workflows_base_dir: {subworkflow_dir}
jobs:
  test:
    name: Test Job
    steps:
      - name: Test step
        run: echo "test"
"""
        workflow_file = tmp_path / "parent.yml"
        workflow_file.write_text(workflow_content)

        workflow_dirs = [tmp_path]
        workflow = find_workflow(str(workflow_file), tuple(workflow_dirs))

        ctx = RunContext(workflow_dirs=workflow_dirs, output_path=tmp_path / "output")
        runner = WorkflowRunner(workflow, ctx)

        await runner._pre_run()

        assert runner.ctx.workflow_dir == workflow_file.parent
        assert subworkflow_dir.absolute() in runner.ctx.workflow_dirs

    @pytest.mark.asyncio
    async def test_dispatch_inputs_survive_workflow_dir_update(self, tmp_path):
        """Dispatch alias/default processing must survive later context updates."""
        workflow_content = """
name: dispatch_workflow
dispatch:
  inputs:
    target:
      required: true
      type: string
      alias: domain
    mode:
      type: string
      default: fast
defaults:
  workflows_base_dir: .
jobs:
  test:
    steps:
      - name: Test step
        run: echo "test"
"""
        workflow_file = tmp_path / "dispatch.yml"
        workflow_file.write_text(workflow_content)

        workflow = find_workflow(str(workflow_file), (tmp_path,))
        ctx = RunContext(inputs={"domain": "example.com"}, output_path=tmp_path / "output")
        runner = WorkflowRunner(workflow, ctx)

        await runner._pre_run()

        assert runner.ctx.inputs["target"] == "example.com"
        assert runner.ctx.inputs["mode"] == "fast"

    @pytest.mark.asyncio
    async def test_dispatch_list_inputs_expand_to_matrix_without_direct_ctx_mutation(
        self, tmp_path
    ):
        """Dispatch list inputs should become matrix values and leave scalar inputs clean."""
        workflow_content = """
name: dispatch_matrix_workflow
dispatch:
  inputs:
    target:
      required: true
      type: string
defaults:
  workflows_base_dir: .
jobs:
  test:
    steps:
      - name: Test step
        run: "echo ${{ inputs.target }}"
"""
        workflow_file = tmp_path / "dispatch-matrix.yml"
        workflow_file.write_text(workflow_content)

        workflow = find_workflow(str(workflow_file), (tmp_path,))
        ctx = RunContext(
            inputs={"target": ["example.com", "example.org"]},
            output_path=tmp_path / "output",
        )
        runner = WorkflowRunner(workflow, ctx)

        await runner._pre_run()

        assert "target" not in runner.ctx.inputs
        assert runner.ctx.vars["_matrix_input_keys"] == ["target"]
        assert runner.model.jobs["test"].strategy is not None
        assert runner.model.jobs["test"].strategy.matrix["target"] == [
            "example.com",
            "example.org",
        ]

    @pytest.mark.asyncio
    async def test_reusable_call_inputs_survive_workflow_dir_update(self, tmp_path):
        """Reusable workflow call input processing must survive later context updates."""
        workflow_content = """
name: reusable_workflow
call:
  inputs:
    target:
      required: true
      type: string
      alias: domain
    mode:
      type: string
      default: fast
defaults:
  workflows_base_dir: .
jobs:
  test:
    steps:
      - name: Test step
        run: echo "test"
"""
        workflow_file = tmp_path / "reusable.yml"
        workflow_file.write_text(workflow_content)

        workflow = find_workflow(str(workflow_file), (tmp_path,))
        ctx = RunContext(inputs={"domain": "example.com"}, output_path=tmp_path / "output")
        runner = WorkflowRunner(workflow, ctx, parent=_ReusableWorkflowParentStub())

        await runner._pre_run()

        assert runner.ctx.inputs["target"] == "example.com"
        assert runner.ctx.inputs["mode"] == "fast"

    def test_model_copy_preserves_workflow_dirs(self):
        """Test that model_copy preserves workflow_dirs"""
        original_dirs = [Path("/original/dir").absolute()]
        ctx = RunContext(workflow_dirs=original_dirs)

        copied_ctx = ctx.model_copy()

        assert copied_ctx.workflow_dirs == original_dirs
        assert copied_ctx.workflow_dirs is not original_dirs

    def test_model_copy_with_update_modifies_workflow_dirs(self):
        """Test that model_copy with update can modify workflow_dirs"""
        original_dirs = [Path("/original/dir").absolute()]
        ctx = RunContext(workflow_dirs=original_dirs)

        new_dirs = [Path("/new/dir").absolute()]
        copied_ctx = ctx.model_copy(update={"workflow_dirs": new_dirs})

        assert copied_ctx.workflow_dirs == new_dirs
        assert ctx.workflow_dirs == original_dirs
