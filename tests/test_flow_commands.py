"""Tests for flow commands: info, visualize, validate, lint, diff, init, list, search."""

from pathlib import Path
import importlib

import pytest
import typer
import yaml
from rich.console import Console

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
    def test_show_info_renders_overview_inputs_jobs_and_outputs(self, workflow_file: Path, monkeypatch):
        import ofx.commands.flow.info as info

        console = Console(record=True, width=120)
        workflow = Workflow.model_validate(yaml.safe_load(workflow_file.read_text()))
        workflow.workflow_path = workflow_file

        monkeypatch.setattr(info, "find_workflow", lambda *_args, **_kwargs: workflow)
        monkeypatch.setattr(info, "get_console", lambda: console)

        info.show_info(str(workflow_file), detailed=True)

        output = console.export_text()
        assert "test-workflow" in output
        assert "A test workflow for validation" in output
        assert "Inputs" in output
        assert "target" in output
        assert "Execution Plan" in output
        assert "job1" in output
        assert "step1" in output
        assert "Job Outputs" in output
        assert "result" in output

    def test_show_info_omits_inputs_when_no_dispatch(self, tmp_path: Path, monkeypatch):
        import ofx.commands.flow.info as info

        console = Console(record=True, width=120)
        wf_data = {key: value for key, value in MINIMAL_WORKFLOW.items() if key != "dispatch"}
        workflow_path = tmp_path / "no-dispatch.yml"
        workflow_path.write_text(yaml.dump(wf_data))
        workflow = Workflow.model_validate(wf_data)
        workflow.workflow_path = workflow_path

        monkeypatch.setattr(info, "find_workflow", lambda *_args, **_kwargs: workflow)
        monkeypatch.setattr(info, "get_console", lambda: console)

        info.show_info(str(workflow_path))

        output = console.export_text()
        assert "Inputs" not in output
        assert "Execution Plan" in output

    def test_show_info_falls_back_to_recursive_workflow_match(self, tmp_path: Path, monkeypatch):
        from ofx.commands.flow.info import show_info

        nested = tmp_path / "nested"
        nested.mkdir()
        flow = nested / "fallback.yml"
        flow.write_text(yaml.dump(MINIMAL_WORKFLOW))

        monkeypatch.setattr("ofx.commands.flow.info.DEFAULT_WORKFLOWS_DIRS", [tmp_path])
        monkeypatch.setattr(
            "ofx.commands.flow.info.find_workflow",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("missing")),
        )

        show_info("fallback")

    def test_step_type_label(self):
        from ofx.runner.step_descriptors import step_type_label
        from ofx.models.step import Step

        assert "task: nmap" in step_type_label(Step(task="nmap", name="s"))
        assert "run:" in step_type_label(Step(run="echo hi", name="s"))
        assert "script" == step_type_label(Step(script="print(1)", name="s"))
        assert "uses:" in step_type_label(Step(uses="./other.yml", name="s"))


class TestFlowCompletions:
    def test_complete_workflow_names_uses_module_search_dirs(self, tmp_path: Path, monkeypatch):
        flow_app = importlib.import_module("ofx.commands.flow.app")

        nested = tmp_path / "recon"
        nested.mkdir()
        (nested / "scan.yml").write_text("name: scan")

        monkeypatch.setattr(flow_app, "get_workflow_search_dirs", lambda: [tmp_path], raising=False)
        monkeypatch.setattr(flow_app, "ALLOWED_WORKFLOW_FILE_EXTENSIONS", {".yml", ".yaml"}, raising=False)
        monkeypatch.setattr("ofx.settings.get_workflow_search_dirs", lambda: [], raising=False)

        assert flow_app._complete_workflow_names("re") == ["recon/"]

    def test_complete_tag_names_uses_module_yaml_loader(self, tmp_path: Path, monkeypatch):
        flow_app = importlib.import_module("ofx.commands.flow.app")

        workflow_path = tmp_path / "scan.yml"
        workflow_path.write_text("name: scan\ntags:\n  - ignored\n")

        monkeypatch.setattr(flow_app, "get_workflow_search_dirs", lambda: [tmp_path], raising=False)
        monkeypatch.setattr(flow_app, "ALLOWED_WORKFLOW_FILE_EXTENSIONS", {".yml", ".yaml"}, raising=False)
        monkeypatch.setattr(flow_app, "yaml_safe_load", lambda _text: {"tags": ["recon"]}, raising=False)
        monkeypatch.setattr("yaml.safe_load", lambda _text: {"tags": ["ignored"]})

        assert flow_app._complete_tag_names("re") == ["recon"]


class TestFlowDiff:
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

    def test_show_diff_reports_added_removed_changed_sections(self, tmp_path: Path, monkeypatch):
        import ofx.commands.flow.diff as diff

        console = Console(record=True, width=120)
        wf_a = {
            "name": "workflow-a",
            "description": "First workflow",
            "tags": ["recon"],
            "env": {"A": "1"},
            "tools": {"httpx": "1.0"},
            "jobs": {"scan": {"steps": [{"name": "s1", "run": "echo a"}]}},
        }
        wf_b = {
            "name": "workflow-b",
            "description": "Second workflow",
            "tags": ["recon", "web"],
            "env": {"A": "2", "B": "3"},
            "tools": {},
            "jobs": {
                "scan": {"steps": [{"name": "s1", "run": "echo a"}]},
                "report": {"steps": [{"name": "s2", "run": "echo report"}]},
            },
        }
        path_a = tmp_path / "wf-a.yml"
        path_b = tmp_path / "wf-b.yml"
        path_a.write_text(yaml.dump(wf_a))
        path_b.write_text(yaml.dump(wf_b))

        monkeypatch.setattr(diff, "get_console", lambda: console)

        diff.show_diff(str(path_a), str(path_b))

        output = console.export_text()
        assert "Tags:" in output
        assert "+ web" in output
        assert "Environment Variables" in output
        assert "added" in output
        assert "changed" in output
        assert "Tools" in output
        assert "removed" in output


class TestFlowVisualize:
    def test_visualize_json_prints_dag_structure(self, workflow_file: Path, monkeypatch):
        import json
        import ofx.commands.flow.visualize as visualize_mod

        console = Console(record=True, width=120)
        workflow = Workflow.model_validate(yaml.safe_load(workflow_file.read_text()))
        workflow.workflow_path = workflow_file

        monkeypatch.setattr(visualize_mod, "_find_workflow_fuzzy", lambda *_args, **_kwargs: workflow)
        monkeypatch.setattr(visualize_mod, "get_console", lambda: console)

        visualize_mod.visualize(str(workflow_file), format="json")

        data = json.loads(console.export_text())
        assert data["name"] == "test-workflow"
        assert len(data["stages"]) == 2
        assert len(data["jobs"]) == 2
        assert len(data["dependencies"]) == 1

    def test_visualize_dot_prints_graphviz_output(self, workflow_file: Path, monkeypatch):
        import ofx.commands.flow.visualize as visualize_mod

        console = Console(record=True, width=120)
        workflow = Workflow.model_validate(yaml.safe_load(workflow_file.read_text()))
        workflow.workflow_path = workflow_file

        monkeypatch.setattr(visualize_mod, "_find_workflow_fuzzy", lambda *_args, **_kwargs: workflow)
        monkeypatch.setattr(visualize_mod, "get_console", lambda: console)

        visualize_mod.visualize(str(workflow_file), format="dot")

        output = console.export_text()
        assert 'digraph "test-workflow"' in output
        assert '"job1" -> "job2"' in output
        assert "cluster_stage" in output

    def test_visualize_json_writes_output_file(self, workflow_file: Path, tmp_path: Path, monkeypatch):
        import json
        import ofx.commands.flow.visualize as visualize_mod

        workflow = Workflow.model_validate(yaml.safe_load(workflow_file.read_text()))
        workflow.workflow_path = workflow_file
        output_path = tmp_path / "workflow.json"
        saved: list[tuple[str, str]] = []

        monkeypatch.setattr(visualize_mod, "_find_workflow_fuzzy", lambda *_args, **_kwargs: workflow)
        monkeypatch.setattr("ofx.commands.ui_helpers.print_success", lambda title, message, **_kwargs: saved.append((title, message)))

        visualize_mod.visualize(str(workflow_file), format="json", output=str(output_path))

        data = json.loads(output_path.read_text())
        assert data["name"] == "test-workflow"
        assert saved == [("Visualization Saved", f"Written to {output_path}")]

    def test_visualize_falls_back_to_recursive_workflow_match(self, tmp_path: Path, monkeypatch):
        from ofx.commands.flow.visualize import visualize

        nested = tmp_path / "nested"
        nested.mkdir()
        flow = nested / "fallback.yml"
        flow.write_text(yaml.dump(MINIMAL_WORKFLOW))

        monkeypatch.setattr("ofx.commands.flow.info.DEFAULT_WORKFLOWS_DIRS", [tmp_path])
        monkeypatch.setattr(
            "ofx.commands.flow.info.find_workflow",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("missing")),
        )

        visualize("fallback", format="json")


class TestFlowValidate:
    def test_validate_workflow_reports_success(self, workflow_file: Path, monkeypatch):
        import ofx.commands.flow.validate as validate

        success_calls: list[tuple[str, str, dict[str, str]]] = []

        monkeypatch.setattr(
            validate,
            "find_workflow",
            lambda *_args, **_kwargs: type("Resolved", (), {"workflow_path": workflow_file})(),
            raising=False,
        )
        monkeypatch.setattr(
            "ofx.commands.ui_helpers.print_info",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "ofx.commands.ui_helpers.print_success",
            lambda title, message, details: success_calls.append((title, message, details)),
        )
        monkeypatch.setattr(validate, "get_console", lambda: Console(record=True, width=120))

        validate.validate_workflows(str(workflow_file), check_tasks=False)

        assert success_calls == [
            (
                "Validation Passed",
                "[cyan]test-workflow[/] is valid",
                {
                    "Path": str(workflow_file),
                    "Jobs": "2",
                    "Steps": "3",
                    "Tags": "test, ci",
                    "Triggers": "dispatch",
                },
            )
        ]

    def test_validate_workflow_reports_invalid_file(self, tmp_path: Path, monkeypatch):
        import ofx.commands.flow.validate as validate

        errors: list[tuple[str, str, str | None]] = []
        bad_file = tmp_path / "bad.yml"
        bad_file.write_text("not: a: valid: workflow")

        def fake_error_exit(title, message, details=None):
            errors.append((title, message, details))
            raise typer.Exit(code=1)

        monkeypatch.setattr(
            validate,
            "find_workflow",
            lambda *_args, **_kwargs: type("Resolved", (), {"workflow_path": bad_file})(),
            raising=False,
        )
        monkeypatch.setattr("ofx.commands.ui_helpers.print_info", lambda *args, **kwargs: None)
        monkeypatch.setattr("ofx.commands.ui_helpers.error_exit", fake_error_exit)
        monkeypatch.setattr(validate, "get_console", lambda: Console(record=True, width=120))

        with pytest.raises(typer.Exit):
            validate.validate_workflows(str(bad_file), check_tasks=False)

        assert errors
        assert errors[0][0] == "Validation Failed"

    def test_validate_workflow_reports_warnings(self, tmp_path: Path, monkeypatch):
        import ofx.commands.flow.validate as validate

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
        console = Console(record=True, width=120)

        monkeypatch.setattr(
            validate,
            "find_workflow",
            lambda *_args, **_kwargs: type("Resolved", (), {"workflow_path": path})(),
            raising=False,
        )
        monkeypatch.setattr("ofx.commands.ui_helpers.print_info", lambda *args, **kwargs: None)
        monkeypatch.setattr("ofx.commands.ui_helpers.print_success", lambda *args, **kwargs: None)
        monkeypatch.setattr(validate, "get_console", lambda: console)

        validate.validate_workflows(str(path), check_tasks=False)

        assert "No dispatch or call trigger defined" in console.export_text()

    def test_validate_all_workflows_uses_module_collection_manager(self, tmp_path: Path, monkeypatch):
        import ofx.commands.flow.validate as validate

        collection_dir = tmp_path / "collection"
        collection_dir.mkdir()
        workflow_path = collection_dir / "bulk.yml"
        workflow_path.write_text(yaml.dump(MINIMAL_WORKFLOW))

        console = Console(record=True, width=120)

        class FakeManager:
            def list_installed(self):
                return {
                    "demo": type("Entry", (), {"path": str(collection_dir)})(),
                }

        class BrokenManager:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("should not use ofx.collections.CollectionManager")

        empty_home = tmp_path / "home"
        (empty_home / ".ofx").mkdir(parents=True)

        monkeypatch.setattr(validate, "BUILTIN_WORKFLOWS_DIR", tmp_path / "builtin-missing")
        monkeypatch.setattr(validate.Path, "home", lambda: empty_home)
        monkeypatch.setattr(validate, "CollectionManager", FakeManager, raising=False)
        monkeypatch.setattr("ofx.collections.CollectionManager", BrokenManager)
        monkeypatch.setattr("ofx.commands.ui_helpers.print_info", lambda *args, **kwargs: None)
        monkeypatch.setattr("ofx.commands.ui_helpers.print_warning", lambda *args, **kwargs: None)
        monkeypatch.setattr(validate, "get_console", lambda: console)

        validate.validate_workflows(all_workflows=True, check_tasks=False)

        output = console.export_text()
        assert "Workflow Validation" in output
        assert "test-workflow" in output


class TestFlowRunSuggestions:
    def test_suggest_similar_workflows_uses_module_workflow_lister(self, monkeypatch):
        import importlib

        flow_run = importlib.import_module("ofx.commands.flow.run")
        warnings: list[str] = []

        monkeypatch.setattr(
            "ofx.utils.workflow_utils.list_available_workflows",
            lambda *_args, **_kwargs: [],
        )
        monkeypatch.setattr(
            flow_run,
            "list_available_workflows",
            lambda *_args, **_kwargs: ["scan-target"],
            raising=False,
        )
        monkeypatch.setattr(flow_run.logger, "warning", warnings.append)

        flow_run.FlowRunHandler("scan-targt")._suggest_similar_workflows()

        assert any("scan-target" in message for message in warnings)

    def test_suggest_similar_workflows_keeps_substring_matching(self, monkeypatch):
        import importlib

        flow_run = importlib.import_module("ofx.commands.flow.run")
        warnings: list[str] = []

        monkeypatch.setattr(
            "ofx.utils.workflow_utils.list_available_workflows",
            lambda *_args, **_kwargs: [],
        )
        monkeypatch.setattr(
            flow_run,
            "list_available_workflows",
            lambda *_args, **_kwargs: ["dns-scan"],
            raising=False,
        )
        monkeypatch.setattr(flow_run.logger, "warning", warnings.append)

        flow_run.FlowRunHandler("scan")._suggest_similar_workflows()

        assert any("dns-scan" in message for message in warnings)


class TestFlowLint:
    def test_lint_workflow_reports_single_output(self, workflow_file: Path, monkeypatch):
        import ofx.commands.flow.lint as lint

        console = Console(record=True, width=120)

        monkeypatch.setattr(
            lint,
            "find_workflow",
            lambda *_args, **_kwargs: type("Resolved", (), {"workflow_path": workflow_file})(),
            raising=False,
        )
        monkeypatch.setattr(lint, "get_console", lambda: console)

        lint.lint_workflows(workflow_name=str(workflow_file))

        output = console.export_text()
        assert "test-workflow" in output
        assert "Job has no outputs declared" in output
        assert "0 errors, 0 warnings, 1 info" in output

    def test_lint_workflow_reports_warnings(self, tmp_path: Path, monkeypatch):
        import ofx.commands.flow.lint as lint

        wf_data = {
            "name": "no-desc",
            "jobs": {"j": {"steps": [{"name": "s", "run": "echo"}]}},
        }
        path = tmp_path / "no-desc.yml"
        path.write_text(yaml.dump(wf_data))
        console = Console(record=True, width=120)

        monkeypatch.setattr(
            lint,
            "find_workflow",
            lambda *_args, **_kwargs: type("Resolved", (), {"workflow_path": path})(),
            raising=False,
        )
        monkeypatch.setattr(lint, "get_console", lambda: console)

        lint.lint_workflows(workflow_name=str(path))

        output = console.export_text()
        assert "Missing or default description" in output
        assert "No tags defined" in output

    def test_lint_workflow_reports_invalid_yaml(self, tmp_path: Path, monkeypatch):
        import ofx.commands.flow.lint as lint

        path = tmp_path / "bad.yml"
        path.write_text("invalid: yaml: content")
        console = Console(record=True, width=120)

        monkeypatch.setattr(
            lint,
            "find_workflow",
            lambda *_args, **_kwargs: type("Resolved", (), {"workflow_path": path})(),
            raising=False,
        )
        monkeypatch.setattr(lint, "get_console", lambda: console)

        lint.lint_workflows(workflow_name=str(path))

        assert "Invalid YAML/schema" in console.export_text()

    def test_lint_all_workflows_uses_module_collection_manager(self, tmp_path: Path, monkeypatch):
        import ofx.commands.flow.lint as lint

        collection_dir = tmp_path / "collection"
        collection_dir.mkdir()
        workflow_path = collection_dir / "bulk.yml"
        workflow_path.write_text(yaml.dump(MINIMAL_WORKFLOW))
        console = Console(record=True, width=120)

        class FakeManager:
            def list_installed(self):
                return {
                    "demo": type("Entry", (), {"path": str(collection_dir)})(),
                }

        class BrokenManager:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("should not use ofx.collections.CollectionManager")

        empty_home = tmp_path / "home"
        (empty_home / ".ofx").mkdir(parents=True)

        monkeypatch.setattr(lint, "BUILTIN_WORKFLOWS_DIR", tmp_path / "builtin-missing")
        monkeypatch.setattr(lint.Path, "home", lambda: empty_home)
        monkeypatch.setattr(lint, "CollectionManager", FakeManager, raising=False)
        monkeypatch.setattr("ofx.collections.CollectionManager", BrokenManager)
        monkeypatch.setattr("ofx.commands.ui_helpers.print_info", lambda *args, **kwargs: None)
        monkeypatch.setattr("ofx.commands.ui_helpers.print_warning", lambda *args, **kwargs: None)
        monkeypatch.setattr(lint, "get_console", lambda: console)

        lint.lint_workflows(all_workflows=True)

        output = console.export_text()
        assert "Lint Issues" in output
        assert "test-workflow" in output


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

    def test_show_history_formats_relative_times(self, monkeypatch):
        from datetime import UTC, datetime, timedelta

        import ofx.commands.flow.history as history

        now = datetime(2026, 1, 2, tzinfo=UTC)
        console = Console(record=True, width=120)

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now

        monkeypatch.setattr(history, "datetime", FixedDateTime)
        monkeypatch.setattr(
            history,
            "load_history",
            lambda limit, workflow, status: [
                {
                    "run_id": "run-just-now",
                    "workflow": "flow-now",
                    "status": "completed",
                    "elapsed_seconds": 1.0,
                    "timestamp": now.isoformat(),
                },
                {
                    "run_id": "run-minutes",
                    "workflow": "flow-min",
                    "status": "failed",
                    "elapsed_seconds": 75.0,
                    "timestamp": (now - timedelta(minutes=5)).isoformat(),
                },
                {
                    "run_id": "run-hours",
                    "workflow": "flow-hour",
                    "status": "canceled",
                    "elapsed_seconds": 7200.0,
                    "timestamp": (now - timedelta(hours=3)).isoformat(),
                },
                {
                    "run_id": "run-days",
                    "workflow": "flow-day",
                    "status": "queued",
                    "elapsed_seconds": 15.0,
                    "timestamp": (now - timedelta(days=2)).isoformat(),
                },
            ],
        )
        monkeypatch.setattr("ofx.settings.get_console", lambda: console)

        history.show_history()

        output = console.export_text()
        assert "just now" in output
        assert "5m ago" in output
        assert "3h ago" in output
        assert "2d ago" in output

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

    def test_show_list_searches_declared_metadata_name(self, tmp_path: Path, monkeypatch):
        import ofx.commands.flow.list_cmd as list_cmd

        console = Console(record=True, width=120)
        workflow = tmp_path / "searchable.yml"
        workflow.write_text(
            yaml.dump(
                {
                    "name": "my-wf",
                    "description": "A test workflow",
                    "tags": ["recon", "web"],
                }
            )
        )

        monkeypatch.setattr(list_cmd, "BUILTIN_WORKFLOWS_DIR", tmp_path)
        monkeypatch.setattr(list_cmd, "get_console", lambda: console)

        list_cmd.show_list(
            builtin=True,
            search_term="my-wf",
            show_tags=True,
            show_descriptions=True,
        )

        output = console.export_text()
        assert "searchable" in output
        assert "#recon" in output
        assert "A test workflow" in output

    def test_show_list_falls_back_to_stem_for_invalid_yaml(self, tmp_path: Path, monkeypatch):
        import ofx.commands.flow.list_cmd as list_cmd

        console = Console(record=True, width=120)
        bad = tmp_path / "bad.yml"
        bad.write_text("not: valid: yaml: {{")

        monkeypatch.setattr(list_cmd, "BUILTIN_WORKFLOWS_DIR", tmp_path)
        monkeypatch.setattr(list_cmd, "get_console", lambda: console)

        list_cmd.show_list(builtin=True, search_term="bad")

        assert "bad" in console.export_text()

    def test_show_list_ignores_non_workflow_files(self, tmp_path: Path, monkeypatch):
        import ofx.commands.flow.list_cmd as list_cmd

        console = Console(record=True, width=120)
        (tmp_path / "a.yml").write_text("name: a")
        (tmp_path / "b.yaml").write_text("name: b")
        (tmp_path / "c.txt").write_text("not a workflow")

        monkeypatch.setattr(list_cmd, "BUILTIN_WORKFLOWS_DIR", tmp_path)
        monkeypatch.setattr(list_cmd, "get_console", lambda: console)

        list_cmd.show_list(builtin=True)

        output = console.export_text()
        assert "a" in output
        assert "b" in output
        assert "c.txt" not in output


class TestFlowCollectionCommands:
    def test_collection_list_uses_module_manager(self, monkeypatch):
        from typer.testing import CliRunner

        from ofx.collections.manifest import InstalledCollection
        from ofx.commands.flow.collection import app as collection_app

        console = Console(record=True, width=120)

        class FakeManager:
            def list_installed(self):
                return {
                    "demo": InstalledCollection(
                        name="demo",
                        version="1.2.3",
                        source="https://example.com/demo.git",
                        tags=["recon"],
                    )
                }

        monkeypatch.setattr(
            "ofx.commands.flow.collection.CollectionManager",
            FakeManager,
            raising=False,
        )
        monkeypatch.setattr("ofx.commands.flow.collection.get_console", lambda: console)

        result = CliRunner().invoke(collection_app, ["list"])

        assert result.exit_code == 0
        output = console.export_text()
        assert "demo" in output
        assert "1.2.3" in output

    def test_collection_info_uses_module_manager(self, monkeypatch, tmp_path: Path):
        from typer.testing import CliRunner

        from ofx.collections.manifest import InstalledCollection
        from ofx.commands.flow.collection import app as collection_app

        console = Console(record=True, width=120)
        coll_dir = tmp_path / "demo"
        coll_dir.mkdir()
        (coll_dir / "scan.yml").write_text("name: scan")

        class FakeManager:
            def get(self, name):
                if name != "demo":
                    return None
                return InstalledCollection(
                    name="demo",
                    source="https://example.com/demo.git",
                    path=str(coll_dir),
                    pinned_ref="main",
                    installed_at="2026-01-01T00:00:00+00:00",
                )

        monkeypatch.setattr(
            "ofx.commands.flow.collection.CollectionManager",
            FakeManager,
            raising=False,
        )
        monkeypatch.setattr("ofx.commands.flow.collection.get_console", lambda: console)

        result = CliRunner().invoke(collection_app, ["info", "demo"])

        assert result.exit_code == 0
        output = console.export_text()
        assert "demo" in output
        assert "scan.yml" in output


class TestFlowSearchHandler:
    """Tests for the search_cmd handler."""

    def test_show_search_no_results(self, tmp_path: Path, monkeypatch):
        """show_search completes without error when nothing matches."""
        import ofx.settings as settings_mod
        from ofx.commands.flow.search_cmd import show_search

        monkeypatch.setattr(settings_mod, "BUILTIN_WORKFLOWS_DIR", tmp_path / "empty")
        show_search(query="nonexistent_xyz_999")
