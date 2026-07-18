"""Tests for secret redaction in logging output."""

from __future__ import annotations

import logging

import pytest

from ofx.utils.log import SecretRedactFilter, register_secrets, register_sensitive_env

@pytest.fixture(autouse=True)
def _clean_redact_filter():
    """Reset the singleton between tests."""
    filt = SecretRedactFilter.get_instance()
    filt.clear()
    yield
    filt.clear()

class TestSecretRedactFilter:
    def test_redacts_registered_value(self):
        filt = SecretRedactFilter.get_instance()
        filt.register_values({"super_secret_token_123"})

        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "key=super_secret_token_123", (), None
        )
        filt.filter(record)
        assert "super_secret_token_123" not in record.msg
        assert "***" in record.msg

    def test_ignores_short_values(self):
        filt = SecretRedactFilter.get_instance()
        filt.register_values({"ab"})

        record = logging.LogRecord("test", logging.INFO, "", 0, "value=ab", (), None)
        filt.filter(record)
        assert "ab" in record.msg

    def test_redacts_multiple_values(self):
        filt = SecretRedactFilter.get_instance()
        filt.register_values({"alpha_secret", "beta_secret"})

        record = logging.LogRecord(
            "test",
            logging.INFO,
            "",
            0,
            "a=alpha_secret b=beta_secret",
            (),
            None,
        )
        filt.filter(record)
        assert "alpha_secret" not in record.msg
        assert "beta_secret" not in record.msg
        assert record.msg == "a=*** b=***"

    def test_redacts_in_args(self):
        filt = SecretRedactFilter.get_instance()
        filt.register_values({"my_password_val"})

        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "pw=%s", ("my_password_val",), None
        )
        filt.filter(record)
        assert record.args == ("***",)

    def test_redacts_longer_match_first(self):
        """Longer secrets should be redacted before substrings."""
        filt = SecretRedactFilter.get_instance()
        filt.register_values({"abcd", "abcdefgh"})

        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "val=abcdefgh", (), None
        )
        filt.filter(record)
        assert "abcd" not in record.msg
        assert record.msg == "val=***"

    def test_no_registered_values_passes_through(self):
        filt = SecretRedactFilter.get_instance()

        record = logging.LogRecord("test", logging.INFO, "", 0, "hello world", (), None)
        filt.filter(record)
        assert record.msg == "hello world"

    def test_clear_stops_redacting(self):
        filt = SecretRedactFilter.get_instance()
        filt.register_values({"secret_value_1234"})
        filt.clear()

        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "val=secret_value_1234", (), None
        )
        filt.filter(record)
        assert "secret_value_1234" in record.msg

class TestRegisterHelpers:
    def test_register_secrets(self):
        register_secrets({"API_KEY": "sk-12345678", "DB_PASS": "hunter2!"})
        filt = SecretRedactFilter.get_instance()

        record = logging.LogRecord(
            "test",
            logging.INFO,
            "",
            0,
            "connecting with sk-12345678 and hunter2!",
            (),
            None,
        )
        filt.filter(record)
        assert "sk-12345678" not in record.msg
        assert "hunter2!" not in record.msg

    def test_register_secrets_accepts_iterable_values(self):
        register_secrets(["sk-12345678", None, "hunter2!"])
        filt = SecretRedactFilter.get_instance()

        record = logging.LogRecord(
            "test",
            logging.INFO,
            "",
            0,
            "connecting with sk-12345678 and hunter2!",
            (),
            None,
        )
        filt.filter(record)
        assert "sk-12345678" not in record.msg
        assert "hunter2!" not in record.msg

    def test_register_sensitive_env_filters_by_key(self):
        register_sensitive_env(
            {
                "API_KEY": "secret_api_val_1234",
                "NORMAL_VAR": "not_a_secret_1234",
                "DB_PASSWORD": "db_pass_value_123",
            }
        )
        filt = SecretRedactFilter.get_instance()

        record = logging.LogRecord(
            "test",
            logging.INFO,
            "",
            0,
            "api=secret_api_val_1234 normal=not_a_secret_1234 db=db_pass_value_123",
            (),
            None,
        )
        filt.filter(record)
        assert "secret_api_val_1234" not in record.msg
        assert "db_pass_value_123" not in record.msg
        assert "not_a_secret_1234" in record.msg

    def test_register_sensitive_env_matches_token_pattern(self):
        register_sensitive_env(
            {
                "GH_TOKEN": "ghp_abcdefghijk1234",
                "SSH_PASSWORD": "ssh_pass_1234567",
                "BEARER_AUTH": "bearer_val_12345",
            }
        )
        filt = SecretRedactFilter.get_instance()

        msg = "ghp_abcdefghijk1234 ssh_pass_1234567 bearer_val_12345"
        record = logging.LogRecord("test", logging.INFO, "", 0, msg, (), None)
        filt.filter(record)
        assert "ghp_abcdefghijk1234" not in record.msg
        assert "ssh_pass_1234567" not in record.msg
        assert "bearer_val_12345" not in record.msg
