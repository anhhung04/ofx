"""Tests for workflow directory operations and context isolation"""

from pathlib import Path

import pytest
import yaml

from ofx.runner import RunContext, WorkflowRunner
from ofx.utils.workflow_utils import (
    add_workflow_dir,
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

    def test_add_workflow_dir_adds_new_path(self):
        """Test that add_workflow_dir adds a new path to the list"""
        workflow_dirs = [Path("/existing/path")]
        new_path = Path("/new/path")

        result = add_workflow_dir(workflow_dirs, new_path)

        assert new_path.absolute() in result
        assert len(result) == 2

    def test_add_workflow_dir_ignores_duplicate(self):
        """Test that add_workflow_dir doesn't add duplicates"""
        existing_path = Path("/existing/path").absolute()
        workflow_dirs = [existing_path]

        result = add_workflow_dir(workflow_dirs, existing_path)

        assert len(result) == 1
        assert result[0] == existing_path

    def test_add_workflow_dir_converts_string_to_path(self):
        """Test that add_workflow_dir accepts string paths"""
        workflow_dirs = []
        string_path = "/some/path"

        result = add_workflow_dir(workflow_dirs, string_path)

        assert Path(string_path).absolute() in result

    def test_workflow_dirs_with_path_returns_updated_copy(self):
        original = [Path("/existing/path").absolute()]

        result = workflow_dirs_with_path(original, "/new/path")

        assert result is not original
        assert original == [Path("/existing/path").absolute()]
        assert Path("/new/path").absolute() in result

    def test_context_has_default_workflow_dirs(self):
        """Test that RunContext initializes with default workflow_dirs"""
        from ofx.settings import DEFAULT_WORKFLOWS_DIRS

        ctx = RunContext()

        assert isinstance(ctx.workflow_dirs, list)
        assert len(ctx.workflow_dirs) == len(DEFAULT_WORKFLOWS_DIRS)
        for dir in DEFAULT_WORKFLOWS_DIRS:
            assert dir in ctx.workflow_dirs

    def test_workflow_runner_initializes_workflow_dirs(self):
        """Test that WorkflowRunner uses default workflow_dirs from context"""
        from ofx.settings import DEFAULT_WORKFLOWS_DIRS

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
        assert len(ctx.workflow_dirs) == len(DEFAULT_WORKFLOWS_DIRS)

        runner = WorkflowRunner(workflow_obj, ctx)

        assert len(runner.ctx.workflow_dirs) == len(DEFAULT_WORKFLOWS_DIRS)
        for dir in DEFAULT_WORKFLOWS_DIRS:
            assert dir.absolute() in runner.ctx.workflow_dirs

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

        assert workflow1 is not workflow2  # deep copies, not same object
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


class TestExtractSecretRefs:
    """Test selective secret extraction from workflow models."""

    def _make_workflow(self, yaml_str: str):
        from ofx.models.workflow import Workflow

        data = yaml.safe_load(yaml_str)
        return Workflow.model_validate(data)

    def test_dot_access(self):
        from ofx.runner.api import _extract_secret_refs

        wf = self._make_workflow("""
            name: test
            jobs:
              a:
                steps:
                  - run: "echo ${{ secrets.API_KEY }}"
        """)
        assert _extract_secret_refs(wf) == {"API_KEY"}

    def test_bracket_access(self):
        from ofx.runner.api import _extract_secret_refs

        wf = self._make_workflow("""
            name: test
            jobs:
              a:
                steps:
                  - run: 'echo ${{ secrets["DB_PASS"] }}'
        """)
        assert _extract_secret_refs(wf) == {"DB_PASS"}

    def test_multiple_secrets_across_jobs(self):
        from ofx.runner.api import _extract_secret_refs

        wf = self._make_workflow("""
            name: test
            jobs:
              a:
                steps:
                  - run: "curl -H 'Authorization: ${{ secrets.TOKEN }}' ${{ secrets.URL }}"
              b:
                steps:
                  - run: "psql ${{ secrets.DB_CONN }}"
        """)
        assert _extract_secret_refs(wf) == {"TOKEN", "URL", "DB_CONN"}

    def test_no_secrets(self):
        from ofx.runner.api import _extract_secret_refs

        wf = self._make_workflow("""
            name: test
            jobs:
              a:
                steps:
                  - run: echo hello
        """)
        assert _extract_secret_refs(wf) == set()

    def test_secrets_in_env(self):
        from ofx.runner.api import _extract_secret_refs

        wf = self._make_workflow("""
            name: test
            env:
              API_KEY: "${{ secrets.MY_API_KEY }}"
            jobs:
              a:
                steps:
                  - run: echo $API_KEY
        """)
        assert "MY_API_KEY" in _extract_secret_refs(wf)

    def test_secrets_in_step_env(self):
        from ofx.runner.api import _extract_secret_refs

        wf = self._make_workflow("""
            name: test
            jobs:
              a:
                steps:
                  - run: echo $TOKEN
                    env:
                      TOKEN: "${{ secrets.GH_TOKEN }}"
        """)
        assert _extract_secret_refs(wf) == {"GH_TOKEN"}

    def test_deduplication(self):
        from ofx.runner.api import _extract_secret_refs

        wf = self._make_workflow("""
            name: test
            jobs:
              a:
                steps:
                  - run: "${{ secrets.KEY }} and ${{ secrets.KEY }}"
              b:
                steps:
                  - run: "${{ secrets.KEY }}"
        """)
        assert _extract_secret_refs(wf) == {"KEY"}
