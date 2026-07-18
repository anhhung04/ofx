"""Tests for runner/core/credential_store.py."""

from __future__ import annotations

class TestShouldStoreCreds:
    def test_step_true_overrides_all(self):
        from ofx.runner.services.credential_store import should_store_creds

        assert should_store_creds(True, parent_model=None, global_default=False) is True

    def test_step_false_overrides_all(self):
        from ofx.runner.services.credential_store import should_store_creds

        assert (
            should_store_creds(False, parent_model=None, global_default=True) is False
        )

    def test_parent_defaults_store_creds_true(self):
        from unittest.mock import MagicMock

        from ofx.runner.services.credential_store import should_store_creds

        parent = MagicMock()
        parent.defaults.store_creds = True
        assert (
            should_store_creds(None, parent_model=parent, global_default=False) is True
        )

    def test_parent_defaults_store_creds_false(self):
        from unittest.mock import MagicMock

        from ofx.runner.services.credential_store import should_store_creds

        parent = MagicMock()
        parent.defaults.store_creds = False
        assert (
            should_store_creds(None, parent_model=parent, global_default=True) is True
        )

    def test_global_default_used_when_no_step_or_parent(self):
        from ofx.runner.services.credential_store import should_store_creds

        assert should_store_creds(None, parent_model=None, global_default=True) is True
        assert (
            should_store_creds(None, parent_model=None, global_default=False) is False
        )

    def test_falls_back_to_settings(self, monkeypatch):
        import ofx.runner.services.credential_store as mod
        from ofx.runner.services.credential_store import should_store_creds

        monkeypatch.setattr(mod.settings, "auto_store_creds", True)
        assert should_store_creds(None, parent_model=None) is True

        monkeypatch.setattr(mod.settings, "auto_store_creds", False)
        assert should_store_creds(None, parent_model=None) is False

    def test_parent_without_defaults_attr(self):
        """parent_model without 'defaults' attribute falls through gracefully."""
        from ofx.runner.services.credential_store import should_store_creds

        class NoDefaults:
            pass

        assert (
            should_store_creds(None, parent_model=NoDefaults(), global_default=False)
            is False
        )

class TestStoreFromTypedOutputs:
    def test_returns_zero_for_empty_list(self):
        from ofx.runner.services.credential_store import store_from_typed_outputs

        assert store_from_typed_outputs([]) == 0

    def test_returns_zero_for_non_useraccount_outputs(self):
        from ofx.runner.services.credential_store import store_from_typed_outputs
        from ofx.tasks.output_types import Port

        port = Port(ip="10.0.0.1", port=22, protocol="tcp")
        assert store_from_typed_outputs([port]) == 0

    def test_skips_useraccount_without_username(self):
        from ofx.runner.services.credential_store import store_from_typed_outputs
        from ofx.tasks.output_types import UserAccount

        account = UserAccount(username="", password="pass")
        assert store_from_typed_outputs([account]) == 0

    def test_graceful_when_db_unavailable(self, monkeypatch):
        """Should return 0 and log debug when pykeepass is missing."""

        from ofx.runner.services.credential_store import store_from_typed_outputs
        from ofx.tasks.output_types import UserAccount

        account = UserAccount(username="admin", password="secret")

        _original_import = (
            __builtins__.__import__ if hasattr(__builtins__, "__import__") else None
        )

        def mock_import(name, *args, **kwargs):
            if "exegol_history" in name:
                raise ImportError("pykeepass not available")
            return orig(name, *args, **kwargs)

        import builtins

        orig = builtins.__import__

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = store_from_typed_outputs([account])
        assert result == 0

    def test_accepts_sequence(self):
        """Should accept any Sequence, not just list."""
        from ofx.runner.services.credential_store import store_from_typed_outputs

        result = store_from_typed_outputs(())
        assert result == 0

    def test_add_credential_exception_handled(self, monkeypatch):
        """When add_credential raises, exception is caught and stored count is 0."""
        from unittest.mock import MagicMock, patch

        from ofx.runner.services.credential_store import store_from_typed_outputs
        from ofx.tasks.output_types import UserAccount

        account = UserAccount(username="alice", password="pw")

        mock_db = MagicMock()
        mock_db.get_credential.return_value = None
        mock_db.add_credential.side_effect = RuntimeError("DB write failed")

        with patch(
            "ofx.api.creds.exegol_history.ExegolHistoryDB", return_value=mock_db
        ):
            result = store_from_typed_outputs([account])

        assert result == 0

    def test_add_credential_stores_successfully(self, monkeypatch):
        """When add_credential succeeds, stored count increments."""
        from unittest.mock import MagicMock, patch

        from ofx.runner.services.credential_store import store_from_typed_outputs
        from ofx.tasks.output_types import UserAccount

        accounts = [
            UserAccount(username="user1", password="pass1"),
            UserAccount(username="user2", password="pass2"),
        ]

        mock_db = MagicMock()
        mock_db.get_credential.return_value = None

        with patch(
            "ofx.api.creds.exegol_history.ExegolHistoryDB", return_value=mock_db
        ):
            result = store_from_typed_outputs(accounts)

        assert result == 2
        assert mock_db.add_credential.call_count == 2

    def test_duplicate_credential_skipped(self, monkeypatch):
        """Existing credential with same password/hash/domain is skipped."""
        from unittest.mock import MagicMock, patch

        from ofx.runner.services.credential_store import store_from_typed_outputs
        from ofx.tasks.output_types import UserAccount

        account = UserAccount(username="user1", password="secret")
        cred = account.to_credential()

        existing = MagicMock()
        existing.password = cred.password
        existing.hash = cred.hash
        existing.domain = cred.domain

        mock_db = MagicMock()
        mock_db.get_credential.return_value = existing

        with patch(
            "ofx.api.creds.exegol_history.ExegolHistoryDB", return_value=mock_db
        ):
            result = store_from_typed_outputs([account])

        assert result == 0
        mock_db.add_credential.assert_not_called()

    def test_custom_log_fn_called(self, monkeypatch):
        """log_fn parameter should be called when DB is unavailable."""
        import builtins

        from ofx.runner.services.credential_store import store_from_typed_outputs
        from ofx.tasks.output_types import UserAccount

        account = UserAccount(username="bob", password="pw")
        messages: list[str] = []

        orig = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "exegol_history" in name:
                raise ImportError("unavailable")
            return orig(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        store_from_typed_outputs([account], log_fn=messages.append)
        assert any("unavailable" in m or "Credential store" in m for m in messages)

class TestStoreAndLogTypedOutputs:
    def test_logs_standard_success_message_once(self):
        from ofx.runner.services.credential_store import store_and_log_typed_outputs
        from ofx.tasks.output_types import UserAccount

        info_messages: list[str] = []

        result = store_and_log_typed_outputs(
            [UserAccount(username="admin", password="pw")],
            debug_fn=lambda _message: None,
            info_fn=info_messages.append,
        )

        assert result == 0
        assert info_messages == []

    def test_delegates_storage_and_logs_success(self, monkeypatch):
        import ofx.runner.services.credential_store as mod

        info_messages: list[str] = []

        monkeypatch.setattr(mod, "store_from_typed_outputs", lambda *_args, **_kwargs: 2)

        result = mod.store_and_log_typed_outputs(
            [object()],
            debug_fn=lambda _message: None,
            info_fn=info_messages.append,
        )

        assert result == 2
        assert info_messages == ["Stored 2 credential(s) in credential store"]

class TestCredentialStoreHelpers:
    def test_should_store_creds_and_duplicate_matching_behavior(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from ofx.runner.services.credential_store import (
            should_store_creds,
            store_from_typed_outputs,
        )
        from ofx.tasks.output_types import UserAccount

        account = UserAccount(username="user1", password="secret")

        cred = account.to_credential()
        existing = SimpleNamespace(password=cred.password, hash=cred.hash, domain=cred.domain)
        duplicate_db = SimpleNamespace(
            get_credential=lambda _username: existing,
            add_credential=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should not add")),
        )
        with patch(
            "ofx.api.creds.exegol_history.ExegolHistoryDB", return_value=duplicate_db
        ):
            assert store_from_typed_outputs([account], log_fn=lambda _msg: None) == 0
        assert should_store_creds(None, SimpleNamespace(defaults=SimpleNamespace(store_creds=True)), False) is True
        assert should_store_creds(None, SimpleNamespace(defaults=SimpleNamespace(store_creds=False)), False) is False

    def test_store_from_typed_outputs_returns_zero_for_duplicate_or_error(self):
        from types import SimpleNamespace

        from ofx.runner.services.credential_store import (
            store_from_typed_outputs,
        )
        from ofx.tasks.output_types import UserAccount
        from unittest.mock import patch

        account = UserAccount(username="user1", password="secret")
        cred = account.to_credential()
        duplicate_db = SimpleNamespace(
            get_credential=lambda _username: SimpleNamespace(password=cred.password, hash=cred.hash, domain=cred.domain),
            add_credential=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should not add")),
        )
        with patch(
            "ofx.api.creds.exegol_history.ExegolHistoryDB", return_value=duplicate_db
        ):
            assert store_from_typed_outputs([account], log_fn=lambda _msg: None) == 0

        error_db = SimpleNamespace(
            get_credential=lambda _username: None,
            add_credential=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        with patch(
            "ofx.api.creds.exegol_history.ExegolHistoryDB", return_value=error_db
        ):
            assert store_from_typed_outputs([account], log_fn=lambda _msg: None) == 0
