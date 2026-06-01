"""Tests for store-creds model/default resolution behavior."""

from __future__ import annotations

from rich.console import Console

from ofx.runner.tasks.runner import TaskExecution


class TestStoreCredsResolution:
    """Test store-creds resolution (step-level vs global)."""

    def test_step_level_true_overrides_global_false(self):
        """Step store-creds: true wins over global auto_store_creds: false."""
        from ofx.models.step import Step

        step = Step(task="hydra", **{"store-creds": True, "with": {"target": "x"}})
        assert step.store_creds is True

    def test_step_level_false_overrides_global_true(self):
        """Step store-creds: false wins over global auto_store_creds: true."""
        from ofx.models.step import Step

        step = Step(task="hydra", **{"store-creds": False, "with": {"target": "x"}})
        assert step.store_creds is False

    def test_step_level_none_falls_through(self):
        """No step-level store-creds → None (defaults to global)."""
        from ofx.models.step import Step

        step = Step(task="hydra", **{"with": {"target": "x"}})
        assert step.store_creds is None

    def test_task_execution_model_carries_flag(self):
        """TaskExecution model stores store_creds flag."""
        model = TaskExecution(task_name="hydra", target="10.0.0.1", store_creds=True)
        assert model.store_creds is True

    def test_task_execution_default_false(self):
        """TaskExecution defaults store_creds to False."""
        model = TaskExecution(task_name="hydra", target="10.0.0.1")
        assert model.store_creds is False

    def test_task_execution_default_shell_matches_platform_default(self):
        from ofx.settings import DEFAULT_SHELL

        model = TaskExecution(task_name="hydra", target="10.0.0.1")

        assert model.shell == DEFAULT_SHELL


class TestDefaultConfigStoreCreds:
    """Test workflow/job defaults.store-creds field."""

    def test_defaults_store_creds_parses(self):
        """DefaultConfig accepts store-creds field."""
        from ofx.models.config import DefaultConfig

        cfg = DefaultConfig.model_validate({"store-creds": True})
        assert cfg.store_creds is True

    def test_defaults_store_creds_default_false(self):
        from ofx.models.config import DefaultConfig

        cfg = DefaultConfig()
        assert cfg.store_creds is False

    def test_workflow_with_defaults_store_creds(self):
        """Full workflow YAML with defaults.store-creds parses correctly."""
        import yaml

        from ofx.models.workflow import Workflow

        data = yaml.safe_load("""
name: test-creds
defaults:
  store-creds: true
jobs:
  scan:
    steps:
      - task: hydra
        with:
          target: "10.0.0.1"
""")
        wf = Workflow.model_validate(data)
        assert wf.defaults.store_creds is True


class TestValidateStoreCredsWarning:
    """Test that validator warns on store-creds for non-task steps."""

    def test_warns_on_store_creds_for_run_step(self, tmp_path, monkeypatch):
        """store-creds on a 'run:' step triggers a warning."""
        import importlib

        validate = importlib.import_module("ofx.commands.flow.validate")
        console = Console(record=True, width=120)

        wf = tmp_path / "test.yml"
        wf.write_text("""
name: test
jobs:
  j1:
    steps:
      - name: shell-step
        run: echo hi
        store-creds: true
""")
        monkeypatch.setattr(
            "ofx.utils.workflow_utils.find_workflow",
            lambda *_args, **_kwargs: type("Resolved", (), {"workflow_path": wf})(),
        )
        monkeypatch.setattr("ofx.commands.ui_helpers.print_info", lambda *args, **kwargs: None)
        monkeypatch.setattr("ofx.commands.ui_helpers.print_success", lambda *args, **kwargs: None)
        monkeypatch.setattr(validate, "get_console", lambda: console)

        validate.validate_workflows(str(wf), check_tasks=False)

        output = console.export_text()
        assert "store-creds" in output
        assert "non-task" in output

    def test_no_warning_on_store_creds_for_task_step(self, tmp_path, monkeypatch):
        """store-creds on a 'task:' step does NOT trigger a warning."""
        import importlib

        validate = importlib.import_module("ofx.commands.flow.validate")
        console = Console(record=True, width=120)

        wf = tmp_path / "test.yml"
        wf.write_text("""
name: test
jobs:
  j1:
    steps:
      - task: hydra
        store-creds: true
        with:
          target: "10.0.0.1"
""")
        monkeypatch.setattr(
            "ofx.utils.workflow_utils.find_workflow",
            lambda *_args, **_kwargs: type("Resolved", (), {"workflow_path": wf})(),
        )
        monkeypatch.setattr("ofx.commands.ui_helpers.print_info", lambda *args, **kwargs: None)
        monkeypatch.setattr("ofx.commands.ui_helpers.print_success", lambda *args, **kwargs: None)
        monkeypatch.setattr(validate, "get_console", lambda: console)

        validate.validate_workflows(str(wf), check_tasks=False)

        assert "store-creds" not in console.export_text()

    def test_no_warning_when_store_creds_not_set(self, tmp_path, monkeypatch):
        """No store-creds field → no warning."""
        import importlib

        validate = importlib.import_module("ofx.commands.flow.validate")
        console = Console(record=True, width=120)

        wf = tmp_path / "test.yml"
        wf.write_text("""
name: test
jobs:
  j1:
    steps:
      - name: shell-step
        run: echo hi
""")
        monkeypatch.setattr(
            "ofx.utils.workflow_utils.find_workflow",
            lambda *_args, **_kwargs: type("Resolved", (), {"workflow_path": wf})(),
        )
        monkeypatch.setattr("ofx.commands.ui_helpers.print_info", lambda *args, **kwargs: None)
        monkeypatch.setattr("ofx.commands.ui_helpers.print_success", lambda *args, **kwargs: None)
        monkeypatch.setattr(validate, "get_console", lambda: console)

        validate.validate_workflows(str(wf), check_tasks=False)

        assert "store-creds" not in console.export_text()
