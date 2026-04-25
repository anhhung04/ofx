"""Tests for flow commands: info, visualize, validate, lint, diff, init, list, search."""

from pathlib import Path

import pytest
import yaml

from ofx.models.workflow import Workflow

# Minimal valid workflow for testing
MINIMAL_WORKFLOW = {
    "name": "test-workflow",
    "description": "A test workflow for validation",
    "tags": ["test", "ci"],
    "dispatch": {
        "inputs": {
            "target": {
                "required": True,
                "type": "string",
                "description": "Test target",
            }
        }
    },
    "jobs": {
        "job1": {
            "name": "First Job",
            "steps": [{"name": "step1", "run": "echo hello"}],
            "outputs": {"result": "{{ steps.step1.outputs.result }}"},
        },
        "job2": {
            "name": "Second Job",
            "needs": ["job1"],
            "steps": [
                {"name": "step2", "run": "echo world"},
                {"name": "step3", "run": "echo done"},
            ],
        },
    },
}


@pytest.fixture
def workflow_file(tmp_path: Path) -> Path:
    """Create a temporary workflow YAML file."""
    path = tmp_path / "test-workflow.yml"
    path.write_text(yaml.dump(MINIMAL_WORKFLOW))
    return path


@pytest.fixture
def workflow(workflow_file: Path) -> Workflow:
    """Load the test workflow model."""
    data = yaml.safe_load(workflow_file.read_text())
    wf = Workflow.model_validate(data)
    wf.workflow_path = workflow_file
    return wf


class TestFlowInfo:
    def test_build_overview_table(self, workflow: Workflow):
        from ofx.commands.flow.info import _build_overview_table

        table = _build_overview_table(workflow)
        assert table is not None
        assert table.row_count >= 5  # name, desc, tags, jobs, steps

    def test_build_inputs_table(self, workflow: Workflow):
        from ofx.commands.flow.info import _build_inputs_table

        table = _build_inputs_table(workflow)
        assert table is not None
        assert table.row_count == 1  # one input: target

    def test_build_inputs_table_none_when_no_dispatch(self):
        from ofx.commands.flow.info import _build_inputs_table

        wf_data = {k: v for k, v in MINIMAL_WORKFLOW.items() if k != "dispatch"}
        wf = Workflow.model_validate(wf_data)
        assert _build_inputs_table(wf) is None

    def test_build_jobs_tree(self, workflow: Workflow):
        from ofx.commands.flow.info import _build_jobs_tree

        tree = _build_jobs_tree(workflow, detailed=False)
        assert tree is not None

    def test_build_jobs_tree_detailed(self, workflow: Workflow):
        from ofx.commands.flow.info import _build_jobs_tree

        tree = _build_jobs_tree(workflow, detailed=True)
        assert tree is not None

    def test_build_outputs_table(self, workflow: Workflow):
        from ofx.commands.flow.info import _build_outputs_table

        table = _build_outputs_table(workflow)
        assert table is not None
        assert table.row_count == 1  # job1 has outputs

    def test_step_type_label(self):
        from ofx.commands.flow.info import _step_type_label
        from ofx.models.step import Step

        assert "task: nmap" in _step_type_label(Step(task="nmap", name="s"))
        assert "run:" in _step_type_label(Step(run="echo hi", name="s"))
        assert "script" == _step_type_label(Step(script="print(1)", name="s"))
        assert "uses:" in _step_type_label(Step(uses="./other.yml", name="s"))


class TestFlowDiff:
    def test_diff_dicts_added(self):
        from ofx.commands.flow.diff import _diff_dicts

        rows = _diff_dicts({"a": 1}, {"a": 1, "b": 2}, "test")
        assert len(rows) == 1
        assert rows[0][0] == "b"
        assert "added" in rows[0][1]

    def test_diff_dicts_removed(self):
        from ofx.commands.flow.diff import _diff_dicts

        rows = _diff_dicts({"a": 1, "b": 2}, {"a": 1}, "test")
        assert len(rows) == 1
        assert rows[0][0] == "b"
        assert "removed" in rows[0][1]

    def test_diff_dicts_changed(self):
        from ofx.commands.flow.diff import _diff_dicts

        rows = _diff_dicts({"a": 1}, {"a": 2}, "test")
        assert len(rows) == 1
        assert "changed" in rows[0][1]

    def test_diff_dicts_identical(self):
        from ofx.commands.flow.diff import _diff_dicts

        rows = _diff_dicts({"a": 1}, {"a": 1}, "test")
        assert rows == []

    def test_diff_lists(self):
        from ofx.commands.flow.diff import _diff_lists

        added, removed, common = _diff_lists(["a", "b"], ["b", "c"])
        assert added == ["c"]
        assert removed == ["a"]
        assert common == ["b"]

    def test_diff_lists_identical(self):
        from ofx.commands.flow.diff import _diff_lists

        added, removed, common = _diff_lists(["a", "b"], ["a", "b"])
        assert added == []
        assert removed == []
        assert common == ["a", "b"]

    def test_show_diff_identical(self, workflow_file: Path, capsys):
        """show_diff completes without error for identical workflows."""
        from ofx.commands.flow.diff import show_diff

        show_diff(str(workflow_file), str(workflow_file))

    def test_show_diff_different(self, tmp_path: Path):
        """show_diff detects differences between two workflows."""
        from ofx.commands.flow.diff import show_diff

        wf_a = {
            "name": "workflow-a",
            "description": "First workflow",
            "tags": ["recon"],
            "jobs": {"scan": {"steps": [{"name": "s1", "run": "echo a"}]}},
        }
        wf_b = {
            "name": "workflow-b",
            "description": "Second workflow",
            "tags": ["recon", "web"],
            "jobs": {
                "scan": {"steps": [{"name": "s1", "run": "echo b"}]},
                "report": {"steps": [{"name": "s2", "run": "echo report"}]},
            },
        }
        path_a = tmp_path / "wf-a.yml"
        path_b = tmp_path / "wf-b.yml"
        path_a.write_text(yaml.dump(wf_a))
        path_b.write_text(yaml.dump(wf_b))

        show_diff(str(path_a), str(path_b))


class TestFlowVisualize:
    def test_build_dag_data(self, workflow: Workflow):
        from ofx.commands.flow.visualize import _build_dag_data

        data = _build_dag_data(workflow)
        assert data["name"] == "test-workflow"
        assert len(data["stages"]) == 2  # 2 stages
        assert len(data["jobs"]) == 2
        assert len(data["dependencies"]) == 1  # job2 depends on job1

    def test_render_dot(self, workflow: Workflow):
        from ofx.commands.flow.visualize import _render_dot

        dot = _render_dot(workflow)
        assert 'digraph "test-workflow"' in dot
        assert '"job1"' in dot
        assert '"job2"' in dot
        assert '"job1" -> "job2"' in dot
        assert "cluster_stage" in dot

    def test_render_json(self, workflow: Workflow):
        import json

        from ofx.commands.flow.visualize import _render_json

        result = _render_json(workflow)
        data = json.loads(result)
        assert data["name"] == "test-workflow"
        assert "stages" in data
        assert "jobs" in data
        assert "dependencies" in data


class TestFlowValidate:
    def test_validate_one_valid(self, workflow_file: Path):
        from ofx.commands.flow.validate import _validate_one

        result = _validate_one(workflow_file, check_tasks=False)
        assert result.valid
        assert result.name == "test-workflow"
        assert result.jobs == 2
        assert result.steps == 3
        assert result.has_dispatch
        assert "test" in result.tags

    def test_validate_one_invalid(self, tmp_path: Path):
        from ofx.commands.flow.validate import _validate_one

        bad_file = tmp_path / "bad.yml"
        bad_file.write_text("not: a: valid: workflow")
        result = _validate_one(bad_file, check_tasks=False)
        assert not result.valid
        assert result.error

    def test_validate_one_with_warnings(self, tmp_path: Path):
        from ofx.commands.flow.validate import _validate_one

        # Workflow without dispatch (triggers a warning)
        wf_data = {
            "name": "warn-test",
            "jobs": {
                "job1": {
                    "steps": [{"name": "s", "run": "echo"}],
                }
            },
        }
        path = tmp_path / "warn.yml"
        path.write_text(yaml.dump(wf_data))
        result = _validate_one(path, check_tasks=False)
        assert result.valid
        assert any(
            "dispatch" in w.lower() or "call" in w.lower() for w in result.warnings
        )


class TestFlowLint:
    def test_lint_clean_workflow(self, workflow_file: Path):
        from ofx.commands.flow.lint import _lint_workflow

        result = _lint_workflow(workflow_file)
        assert result.name == "test-workflow"
        # Should have some info issues (job2 has no outputs) but no errors/warns
        assert result.error_count == 0
        assert result.warn_count == 0

    def test_lint_missing_description(self, tmp_path: Path):
        from ofx.commands.flow.lint import _lint_workflow

        wf_data = {
            "name": "no-desc",
            "jobs": {"j": {"steps": [{"name": "s", "run": "echo"}]}},
        }
        path = tmp_path / "no-desc.yml"
        path.write_text(yaml.dump(wf_data))
        result = _lint_workflow(path)
        assert any("description" in i.message.lower() for i in result.issues)

    def test_lint_missing_tags(self, tmp_path: Path):
        from ofx.commands.flow.lint import _lint_workflow

        wf_data = {
            "name": "no-tags",
            "description": "Has desc but no tags",
            "jobs": {"j": {"steps": [{"name": "s", "run": "echo"}]}},
        }
        path = tmp_path / "no-tags.yml"
        path.write_text(yaml.dump(wf_data))
        result = _lint_workflow(path)
        assert any("tags" in i.message.lower() for i in result.issues)

    def test_lint_invalid_yaml(self, tmp_path: Path):
        from ofx.commands.flow.lint import _lint_workflow

        path = tmp_path / "bad.yml"
        path.write_text("invalid: yaml: content")
        result = _lint_workflow(path)
        assert result.error_count > 0


class TestFlowHistory:
    """Tests for flow run history tracking."""

    def test_save_and_load(self, tmp_path: Path, monkeypatch):
        from ofx.commands.flow import history

        monkeypatch.setattr(history, "HISTORY_DIR", tmp_path)
        monkeypatch.setattr(history, "HISTORY_FILE", tmp_path / "runs.ndjson")

        history.save_run_record(
            run_id="abc-123",
            workflow_name="test-flow",
            status="completed",
            elapsed_seconds=12.5,
        )
        history.save_run_record(
            run_id="def-456",
            workflow_name="other-flow",
            status="failed",
            error="something broke",
            elapsed_seconds=3.2,
        )

        records = history.load_history(limit=10)
        assert len(records) == 2
        assert records[0]["run_id"] == "def-456"  # newest first
        assert records[1]["run_id"] == "abc-123"

    def test_filter_by_workflow(self, tmp_path: Path, monkeypatch):
        from ofx.commands.flow import history

        monkeypatch.setattr(history, "HISTORY_DIR", tmp_path)
        monkeypatch.setattr(history, "HISTORY_FILE", tmp_path / "runs.ndjson")

        history.save_run_record(
            run_id="1", workflow_name="scan-target", status="completed"
        )
        history.save_run_record(
            run_id="2", workflow_name="recon-dns", status="completed"
        )

        records = history.load_history(workflow="scan")
        assert len(records) == 1
        assert records[0]["workflow"] == "scan-target"

    def test_filter_by_status(self, tmp_path: Path, monkeypatch):
        from ofx.commands.flow import history

        monkeypatch.setattr(history, "HISTORY_DIR", tmp_path)
        monkeypatch.setattr(history, "HISTORY_FILE", tmp_path / "runs.ndjson")

        history.save_run_record(run_id="1", workflow_name="a", status="completed")
        history.save_run_record(run_id="2", workflow_name="b", status="failed")

        records = history.load_history(status="failed")
        assert len(records) == 1
        assert records[0]["status"] == "failed"

    def test_clear_history(self, tmp_path: Path, monkeypatch):
        from ofx.commands.flow import history

        monkeypatch.setattr(history, "HISTORY_DIR", tmp_path)
        monkeypatch.setattr(history, "HISTORY_FILE", tmp_path / "runs.ndjson")

        history.save_run_record(run_id="1", workflow_name="a", status="completed")
        history.save_run_record(run_id="2", workflow_name="b", status="completed")

        count = history.clear_history()
        assert count == 2
        assert history.load_history() == []

    def test_prune_history(self, tmp_path: Path, monkeypatch):
        from ofx.commands.flow import history

        monkeypatch.setattr(history, "HISTORY_DIR", tmp_path)
        monkeypatch.setattr(history, "HISTORY_FILE", tmp_path / "runs.ndjson")

        for i in range(10):
            history.save_run_record(
                run_id=str(i), workflow_name=f"flow-{i}", status="completed"
            )

        pruned = history.prune_history(keep=3)
        assert pruned == 7
        records = history.load_history(limit=100)
        assert len(records) == 3

    def test_relative_time(self):
        from datetime import UTC, datetime, timedelta

        from ofx.commands.flow.history import _relative_time

        now = datetime.now(UTC)
        assert _relative_time(now.isoformat()) == "just now"
        assert "m ago" in _relative_time((now - timedelta(minutes=5)).isoformat())
        assert "h ago" in _relative_time((now - timedelta(hours=3)).isoformat())
        assert "d ago" in _relative_time((now - timedelta(days=2)).isoformat())

    def test_empty_history(self, tmp_path: Path, monkeypatch):
        from ofx.commands.flow import history

        monkeypatch.setattr(history, "HISTORY_DIR", tmp_path)
        monkeypatch.setattr(history, "HISTORY_FILE", tmp_path / "runs.ndjson")

        records = history.load_history()
        assert records == []


class TestFlowCommandExitCodes:
    """Verify that flow subcommands exit non-zero on error conditions."""

    def _invoke(self, args: list[str]):
        from typer.testing import CliRunner

        from ofx.commands.__init__ import _register_commands, app

        runner = CliRunner()
        _register_commands()
        return runner.invoke(app, args)

    def test_validate_missing_argument(self):
        result = self._invoke(["flow", "validate"])
        assert result.exit_code != 0

    def test_validate_nonexistent_workflow(self):
        result = self._invoke(["flow", "validate", "nonexistent_workflow_xyz_999"])
        assert result.exit_code != 0

    def test_info_nonexistent_workflow(self):
        result = self._invoke(["flow", "info", "nonexistent_workflow_xyz_999"])
        assert result.exit_code != 0

    def test_lint_missing_argument(self):
        result = self._invoke(["flow", "lint"])
        assert result.exit_code != 0

    def test_diff_nonexistent_first_workflow(self):
        result = self._invoke(
            ["flow", "diff", "nonexistent_a_999", "nonexistent_b_999"]
        )
        assert result.exit_code != 0

    def test_visualize_nonexistent_workflow(self):
        result = self._invoke(["flow", "visualize", "nonexistent_workflow_xyz_999"])
        assert result.exit_code != 0

    def test_validate_valid_workflow(self, workflow_file: Path):
        result = self._invoke(["flow", "validate", str(workflow_file)])
        assert result.exit_code == 0

    def test_info_valid_workflow(self, workflow_file: Path):
        result = self._invoke(["flow", "info", str(workflow_file)])
        assert result.exit_code == 0

    def test_lint_valid_workflow(self, workflow_file: Path):
        result = self._invoke(["flow", "lint", str(workflow_file)])
        assert result.exit_code == 0

    def test_visualize_valid_workflow_terminal(self, workflow_file: Path):
        result = self._invoke(
            ["flow", "visualize", str(workflow_file), "--format", "terminal"]
        )
        assert result.exit_code == 0

    def test_visualize_valid_workflow_dot(self, workflow_file: Path):
        result = self._invoke(
            ["flow", "visualize", str(workflow_file), "--format", "dot"]
        )
        assert result.exit_code == 0

    def test_visualize_valid_workflow_json(self, workflow_file: Path):
        result = self._invoke(
            ["flow", "visualize", str(workflow_file), "--format", "json"]
        )
        assert result.exit_code == 0

    def test_visualize_invalid_format_rejected(self, workflow_file: Path):
        result = self._invoke(
            ["flow", "visualize", str(workflow_file), "--format", "mermaid"]
        )
        assert result.exit_code != 0


class TestFlowInit:
    """Tests for the flow init command and FlowInitHandler."""

    def test_handler_creates_file(self, tmp_path: Path):
        from ofx.commands.flow.init import FlowInitHandler

        handler = FlowInitHandler()
        handler.run(
            workflow_name="my-scan", output=str(tmp_path / "my-scan.yml"), force=False
        )

        out_file = tmp_path / "my-scan.yml"
        assert out_file.exists()
        content = out_file.read_text()
        assert "name: my-scan" in content
        assert "yaml-language-server" in content

    def test_handler_refuses_overwrite_without_force(self, tmp_path: Path):
        from click.exceptions import Exit

        from ofx.commands.flow.init import FlowInitHandler

        out_file = tmp_path / "existing.yml"
        out_file.write_text("already here")

        handler = FlowInitHandler()
        with pytest.raises(Exit):
            handler.run(workflow_name="existing", output=str(out_file), force=False)

    def test_handler_overwrites_with_force(self, tmp_path: Path):
        from ofx.commands.flow.init import FlowInitHandler

        out_file = tmp_path / "overwrite.yml"
        out_file.write_text("old content")

        handler = FlowInitHandler()
        handler.run(workflow_name="overwrite", output=str(out_file), force=True)

        assert "name: overwrite" in out_file.read_text()

    def test_handler_output_directory(self, tmp_path: Path):
        from ofx.commands.flow.init import FlowInitHandler

        handler = FlowInitHandler()
        handler.run(workflow_name="dir-test", output=str(tmp_path), force=False)

        assert (tmp_path / "dir-test.yml").exists()

    def test_handler_default_output(self, tmp_path: Path, monkeypatch):
        from ofx.commands.flow.init import FlowInitHandler

        monkeypatch.chdir(tmp_path)
        handler = FlowInitHandler()
        handler.run(workflow_name="default-name", output="", force=False)

        assert (tmp_path / "default-name.yml").exists()

    def test_generated_workflow_is_valid_yaml(self, tmp_path: Path):
        """The generated scaffold should parse as valid YAML."""
        from ofx.commands.flow.init import FlowInitHandler

        handler = FlowInitHandler()
        out_file = tmp_path / "valid-check.yml"
        handler.run(workflow_name="valid-check", output=str(out_file), force=False)

        data = yaml.safe_load(out_file.read_text())
        assert isinstance(data, dict)
        assert data["name"] == "valid-check"
        assert "jobs" in data


class TestFlowListHandler:
    """Tests for the list_cmd handler."""

    def test_show_list_no_workflows(self, tmp_path: Path, monkeypatch):
        """show_list completes without error when no workflows exist."""
        import ofx.settings as settings_mod

        from ofx.commands.flow.list_cmd import show_list

        monkeypatch.setattr(settings_mod, "BUILTIN_WORKFLOWS_DIR", tmp_path / "empty")
        show_list(builtin=True)

    def test_read_metadata(self, tmp_path: Path):
        from ofx.commands.flow.list_cmd import _read_metadata

        wf = tmp_path / "test.yml"
        wf.write_text(
            yaml.dump(
                {"name": "my-wf", "description": "A test", "tags": ["recon", "web"]}
            )
        )

        meta = _read_metadata(wf)
        assert meta["name"] == "my-wf"
        assert meta["description"] == "A test"
        assert "recon" in meta["tags"]

    def test_read_metadata_invalid(self, tmp_path: Path):
        from ofx.commands.flow.list_cmd import _read_metadata

        bad = tmp_path / "bad.yml"
        bad.write_text("not: valid: yaml: {{")

        meta = _read_metadata(bad)
        assert meta["name"] == "bad"
        assert meta["tags"] == []

    def test_scan_yaml_files(self, tmp_path: Path):
        from ofx.commands.flow.list_cmd import _scan_yaml_files

        (tmp_path / "a.yml").write_text("name: a")
        (tmp_path / "b.yaml").write_text("name: b")
        (tmp_path / "c.txt").write_text("not a workflow")

        files = _scan_yaml_files(tmp_path)
        names = {f.name for f in files}
        assert "a.yml" in names
        assert "b.yaml" in names
        assert "c.txt" not in names


class TestFlowSearchHandler:
    """Tests for the search_cmd handler."""

    def test_show_search_no_results(self, tmp_path: Path, monkeypatch):
        """show_search completes without error when nothing matches."""
        import ofx.settings as settings_mod

        from ofx.commands.flow.search_cmd import show_search

        monkeypatch.setattr(settings_mod, "BUILTIN_WORKFLOWS_DIR", tmp_path / "empty")
        show_search(query="nonexistent_xyz_999")
