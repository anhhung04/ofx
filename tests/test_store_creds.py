"""Tests for task output → credential store integration."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from ofx.runner.tasks.runner import TaskExecution, TaskRunner
from ofx.tasks.output_types import UserAccount


class TestStoreCredentials:
    """Unit tests for TaskRunner._store_credentials()."""

    def _make_runner(self, store_creds: bool = True) -> TaskRunner:
        from ofx.runner.context import RunContext

        model = TaskExecution(
            task_name="hydra", target="10.0.0.1", store_creds=store_creds
        )
        ctx = RunContext()
        runner = TaskRunner(model, ctx)
        return runner

    def test_no_user_accounts_returns_zero(self):
        """No UserAccount items → 0 stored."""
        from ofx.tasks.output_types import Port

        runner = self._make_runner()
        result = runner._store_credentials([Port(ip="10.0.0.1", port=22)])
        assert result == 0

    def test_empty_list_returns_zero(self):
        runner = self._make_runner()
        assert runner._store_credentials([]) == 0

    @patch(
        "ofx.api.creds.exegol_history.ExegolHistoryDB",
        side_effect=ImportError("no pykeepass"),
    )
    def test_import_error_returns_zero(self, _mock):
        """Missing pykeepass → graceful fallback."""
        runner = self._make_runner()
        accounts = [UserAccount(username="admin", password="pass123")]
        result = runner._store_credentials(accounts)
        assert result == 0

    @patch(
        "ofx.api.creds.exegol_history.ExegolHistoryDB",
        side_effect=FileNotFoundError("no DB"),
    )
    def test_file_not_found_returns_zero(self, _mock):
        """Missing DB file → graceful fallback."""
        runner = self._make_runner()
        accounts = [UserAccount(username="admin", password="pass123")]
        result = runner._store_credentials(accounts)
        assert result == 0

    def test_stores_new_credentials(self):
        """New credentials are stored via add_credential()."""
        runner = self._make_runner()
        mock_db = MagicMock()
        mock_db.get_credential.return_value = None  # No existing cred

        accounts = [
            UserAccount(username="admin", password="pass123", domain="corp.local"),
            UserAccount(username="svc_sql", password="", hash="aad3b435:abcdef"),
        ]

        with patch(
            "ofx.api.creds.exegol_history.ExegolHistoryDB", return_value=mock_db
        ):
            result = runner._store_credentials(accounts)

        assert result == 2
        assert mock_db.add_credential.call_count == 2

        # Verify first call
        call1 = mock_db.add_credential.call_args_list[0]
        assert call1.kwargs["username"] == "admin"
        assert call1.kwargs["password"] == "pass123"
        assert call1.kwargs["domain"] == "corp.local"

        # Verify second call
        call2 = mock_db.add_credential.call_args_list[1]
        assert call2.kwargs["username"] == "svc_sql"
        assert call2.kwargs["hash_value"] == "aad3b435:abcdef"

    def test_skips_duplicate_credentials(self):
        """Exact duplicate (same user+pass+hash+domain) is skipped."""
        runner = self._make_runner()
        mock_db = MagicMock()

        # Existing credential matches
        @dataclass
        class FakeCred:
            password: str = "pass123"
            hash: str = ""
            domain: str = "corp.local"

        mock_db.get_credential.return_value = FakeCred()

        accounts = [
            UserAccount(username="admin", password="pass123", domain="corp.local"),
        ]

        with patch(
            "ofx.api.creds.exegol_history.ExegolHistoryDB", return_value=mock_db
        ):
            result = runner._store_credentials(accounts)

        assert result == 0
        mock_db.add_credential.assert_not_called()

    def test_stores_when_password_differs(self):
        """Same username but different password → stores as new."""
        runner = self._make_runner()
        mock_db = MagicMock()

        @dataclass
        class FakeCred:
            password: str = "old_pass"
            hash: str = ""
            domain: str = "corp.local"

        mock_db.get_credential.return_value = FakeCred()

        accounts = [
            UserAccount(username="admin", password="new_pass", domain="corp.local"),
        ]

        with patch(
            "ofx.api.creds.exegol_history.ExegolHistoryDB", return_value=mock_db
        ):
            result = runner._store_credentials(accounts)

        assert result == 1
        mock_db.add_credential.assert_called_once()

    def test_skips_empty_username(self):
        """Accounts with no username are skipped."""
        runner = self._make_runner()
        mock_db = MagicMock()
        mock_db.get_credential.return_value = None

        accounts = [
            UserAccount(username="", password="pass123"),
            UserAccount(username="admin", password="pass123"),
        ]

        with patch(
            "ofx.api.creds.exegol_history.ExegolHistoryDB", return_value=mock_db
        ):
            result = runner._store_credentials(accounts)

        assert result == 1

    def test_credential_comment_includes_metadata(self):
        """UserAccount metadata (host, source, type) flows into comment."""
        runner = self._make_runner()
        mock_db = MagicMock()
        mock_db.get_credential.return_value = None

        accounts = [
            UserAccount(
                username="admin",
                password="pass",
                host="10.0.0.1",
                source="hydra",
                account_type="local",
                privilege_level="admin",
            ),
        ]

        with patch(
            "ofx.api.creds.exegol_history.ExegolHistoryDB", return_value=mock_db
        ):
            runner._store_credentials(accounts)

        call = mock_db.add_credential.call_args
        comment = call.kwargs["comment"]
        assert "host=10.0.0.1" in comment
        assert "source=hydra" in comment
        assert "type=local" in comment
        assert "priv=admin" in comment

    def test_mixed_output_types_filters_user_accounts(self):
        """Only UserAccount items are stored, others ignored."""
        from ofx.tasks.output_types import Port, Vulnerability

        runner = self._make_runner()
        mock_db = MagicMock()
        mock_db.get_credential.return_value = None

        items = [
            Port(ip="10.0.0.1", port=22),
            UserAccount(username="admin", password="pass"),
            Vulnerability(name="CVE-2024-1234"),
            UserAccount(username="root", password="toor"),
        ]

        with patch(
            "ofx.api.creds.exegol_history.ExegolHistoryDB", return_value=mock_db
        ):
            result = runner._store_credentials(items)

        assert result == 2


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

    def test_warns_on_store_creds_for_run_step(self, tmp_path):
        """store-creds on a 'run:' step triggers a warning."""
        from ofx.commands.flow.validate import _validate_one

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
        result = _validate_one(wf, check_tasks=False)
        assert result.valid
        assert any("store-creds" in w and "non-task" in w for w in result.warnings)

    def test_no_warning_on_store_creds_for_task_step(self, tmp_path):
        """store-creds on a 'task:' step does NOT trigger a warning."""
        from ofx.commands.flow.validate import _validate_one

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
        result = _validate_one(wf, check_tasks=False)
        assert result.valid
        assert not any("store-creds" in w for w in result.warnings)

    def test_no_warning_when_store_creds_not_set(self, tmp_path):
        """No store-creds field → no warning."""
        from ofx.commands.flow.validate import _validate_one

        wf = tmp_path / "test.yml"
        wf.write_text("""
name: test
jobs:
  j1:
    steps:
      - name: shell-step
        run: echo hi
""")
        result = _validate_one(wf, check_tasks=False)
        assert result.valid
        assert not any("store-creds" in w for w in result.warnings)
