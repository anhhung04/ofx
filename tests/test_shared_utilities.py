"""Tests for shared runner utilities: matrix_utils, credential_store, step_output."""

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# MatrixCombinationBuilder
# ---------------------------------------------------------------------------
from ofx.runner.core.matrix_utils import (
    MAX_MATRIX_COMBINATIONS,
    estimate_matrix_count,
    generate_matrix_combinations,
)


class TestMatrixCombinationBuilder:
    def test_empty_matrix(self):
        assert generate_matrix_combinations(None) == []
        assert generate_matrix_combinations({}) == []

    def test_single_key(self):
        result = generate_matrix_combinations({"os": ["linux", "windows"]})
        assert result == [{"os": "linux"}, {"os": "windows"}]

    def test_cartesian_product(self):
        result = generate_matrix_combinations(
            {"os": ["linux", "windows"], "arch": ["x64", "arm"]}
        )
        assert len(result) == 4
        assert {"os": "linux", "arch": "x64"} in result
        assert {"os": "windows", "arch": "arm"} in result

    def test_exclude_filter(self):
        result = generate_matrix_combinations(
            {"os": ["linux", "windows"], "arch": ["x64", "arm"]},
            exclude=[{"os": "windows", "arch": "arm"}],
        )
        assert len(result) == 3
        assert {"os": "windows", "arch": "arm"} not in result

    def test_include_appends(self):
        result = generate_matrix_combinations(
            {"os": ["linux"]},
            include=[{"os": "macos"}],
        )
        assert len(result) == 2
        assert {"os": "macos"} in result

    def test_include_no_duplicate(self):
        result = generate_matrix_combinations(
            {"os": ["linux", "windows"]},
            include=[{"os": "linux"}],
        )
        assert len(result) == 2

    def test_exclude_then_include(self):
        result = generate_matrix_combinations(
            {"os": ["linux", "windows"], "arch": ["x64", "arm"]},
            exclude=[{"os": "windows", "arch": "arm"}],
            include=[{"os": "freebsd", "arch": "x64"}],
        )
        assert len(result) == 4
        assert {"os": "freebsd", "arch": "x64"} in result
        assert {"os": "windows", "arch": "arm"} not in result

    def test_enforce_limit_raises(self):
        big_matrix = {f"k{i}": list(range(20)) for i in range(5)}
        with pytest.raises(ValueError, match="Matrix would produce"):
            generate_matrix_combinations(big_matrix, enforce_limit=True)

    def test_enforce_limit_disabled(self):
        # 3^5 = 243 — fine even with limit
        matrix = {f"k{i}": [1, 2, 3] for i in range(5)}
        result = generate_matrix_combinations(matrix, enforce_limit=False)
        assert len(result) == 243

    def test_estimate_matrix_count(self):
        count = estimate_matrix_count(
            {"os": ["a", "b", "c"], "arch": ["x", "y"]},
            exclude=[{"os": "c", "arch": "y"}],
        )
        assert count == 5  # 6 - 1 excluded

    def test_estimate_empty(self):
        assert estimate_matrix_count(None) == 1
        assert estimate_matrix_count({}) == 1

    def test_all_excluded_returns_empty(self):
        result = generate_matrix_combinations(
            {"os": ["linux"]},
            exclude=[{"os": "linux"}],
        )
        assert result == []


# ---------------------------------------------------------------------------
# CredentialStore
# ---------------------------------------------------------------------------
from ofx.runner.core.credential_store import (
    should_store_creds,
    store_from_typed_outputs,
)


class TestShouldStoreCreds:
    def test_step_explicit_true(self):
        assert should_store_creds(True) is True

    def test_step_explicit_false(self):
        assert should_store_creds(False) is False

    def test_step_none_falls_to_parent(self):
        parent = SimpleNamespace(defaults=SimpleNamespace(store_creds=True))
        assert should_store_creds(None, parent) is True

    def test_step_none_parent_no_defaults(self):
        parent = SimpleNamespace()
        assert should_store_creds(None, parent, global_default=False) is False

    def test_step_none_no_parent_uses_global(self):
        assert should_store_creds(None, None, global_default=True) is True
        assert should_store_creds(None, None, global_default=False) is False

    def test_step_overrides_parent(self):
        parent = SimpleNamespace(defaults=SimpleNamespace(store_creds=True))
        assert should_store_creds(False, parent) is False


class TestStoreFromTypedOutputs:
    def test_empty_list(self):
        assert store_from_typed_outputs([]) == 0

    def test_no_user_accounts(self):
        assert store_from_typed_outputs(["not an account", 42]) == 0

    def test_import_error_graceful(self):
        """When ExegolHistoryDB is unavailable, returns 0 without raising."""
        from ofx.tasks.output_types import UserAccount

        account = UserAccount(username="admin", password="pass123")
        logs = []

        # Patch the import path used inside the function
        with patch.dict("sys.modules", {"ofx.api.creds.exegol_history": None}):
            result = store_from_typed_outputs(
                [account], log_fn=logs.append
            )
        assert result == 0
        assert any("unavailable" in m for m in logs)


# ---------------------------------------------------------------------------
# StepOutputHandler
# ---------------------------------------------------------------------------
from ofx.runner.core.step_output import log_output, save_output_file


class TestLogOutput:
    def test_empty_content_skipped(self):
        messages = []
        log_output(messages.append, "stdout", "")
        assert messages == []

    def test_none_content_skipped(self):
        messages = []
        log_output(messages.append, "stdout", None)
        assert messages == []

    def test_short_content_no_truncation(self):
        messages = []
        log_output(messages.append, "stdout", "hello\nworld", max_lines=10)
        assert len(messages) == 1
        assert "===stdout===" in messages[0]
        assert "hello" in messages[0]

    def test_long_content_truncated(self):
        messages = []
        content = "\n".join(f"line {i}" for i in range(100))
        log_output(messages.append, "stdout", content, max_lines=5)
        assert len(messages) == 1
        assert "95 more lines" in messages[0]
        assert "line 0" in messages[0]
        assert "line 4" in messages[0]


class TestSaveOutputFile:
    def test_save_creates_file(self, tmp_path):
        step = SimpleNamespace(
            name="test-step",
            step_index=0,
            run="echo hello",
            uses=None,
            script_file=None,
            script=None,
            task=None,
        )
        result = save_output_file(
            tmp_path, "job1", step, "hello world", {}
        )
        assert result is not None
        assert result.exists()
        content = result.read_text()
        assert ">> command: echo hello" in content
        assert "hello world" in content

    def test_save_with_task_header(self, tmp_path):
        step = SimpleNamespace(
            name="scan",
            step_index=1,
            run=None,
            uses=None,
            script_file=None,
            script=None,
            task="nmap",
        )
        result = save_output_file(tmp_path, "job2", step, "output data")
        content = result.read_text()
        assert ">> task: nmap" in content

    def test_save_with_metadata_flags(self, tmp_path):
        step = SimpleNamespace(
            name="s",
            step_index=0,
            run="cmd",
            uses=None,
            script_file=None,
            script=None,
            task=None,
        )
        outputs = {
            "binary_output": True,
            "output_truncated": True,
            "stderr_truncated": True,
        }
        result = save_output_file(tmp_path, "j", step, "data", outputs)
        content = result.read_text()
        assert "[BINARY OUTPUT]" in content
        assert "[OUTPUT TRUNCATED]" in content
        assert "[STDERR TRUNCATED]" in content

    def test_save_none_output_path(self):
        result = save_output_file(None, "j", SimpleNamespace(), "data")
        assert result is None

    def test_save_with_script_base64(self, tmp_path):
        step = SimpleNamespace(
            name="py",
            step_index=0,
            run=None,
            uses=None,
            script_file=None,
            script="print('hi')",
            task=None,
        )
        result = save_output_file(tmp_path, "j", step, "hi")
        content = result.read_text()
        assert ">> script (base64):" in content


# ---------------------------------------------------------------------------
# Cloud step retry backoff (matching local StepRunner behavior)
# ---------------------------------------------------------------------------
class TestCloudRetryBackoff:
    def test_retry_delay_exponential(self):
        from ofx.runner.execution.cloud_step import CloudStepRunner

        # attempt=0 → base_delay * 2^0 = base_delay
        # attempt=1 → base_delay * 2^1 = 2*base_delay
        # attempt=2 → base_delay * 2^2 = 4*base_delay
        for attempt in range(5):
            delay = CloudStepRunner._retry_delay_seconds(attempt, base_delay=10)
            expected_backoff = 10 * (2**attempt)
            expected_capped = min(expected_backoff, 300)
            # With jitter uniform(0.5, 1.0), delay is in [cap*0.5, cap*1.0]
            assert expected_capped * 0.5 <= delay <= expected_capped * 1.0

    def test_retry_delay_capped_at_300(self):
        from ofx.runner.execution.cloud_step import CloudStepRunner

        # attempt=10 with base_delay=10 → 10*1024 = 10240, capped at 300
        delay = CloudStepRunner._retry_delay_seconds(10, base_delay=10)
        assert delay <= 300

    def test_matches_local_step_runner(self):
        from ofx.runner.execution.cloud_step import CloudStepRunner
        from ofx.runner.execution.step import StepRunner

        # Both should use the same formula
        for attempt in range(5):
            # Can't compare exact values due to jitter, but verify ranges match
            for _ in range(20):
                local = StepRunner._retry_delay_seconds(None, attempt, 10)
                cloud = CloudStepRunner._retry_delay_seconds(attempt, 10)
                # Both capped at 300, both use uniform(0.5, 1.0) jitter
                cap = min(10 * (2**attempt), 300)
                assert cap * 0.5 <= local <= cap
                assert cap * 0.5 <= cloud <= cap
