"""Tests for shared runner utilities: matrix_utils, credential_store, step_output."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ofx.runner.matrix_utils import (
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
        matrix = {f"k{i}": [1, 2, 3] for i in range(5)}
        result = generate_matrix_combinations(matrix, enforce_limit=False)
        assert len(result) == 243

    def test_estimate_matrix_count(self):
        count = estimate_matrix_count(
            {"os": ["a", "b", "c"], "arch": ["x", "y"]},
            exclude=[{"os": "c", "arch": "y"}],
        )
        assert count == 5

    def test_estimate_empty(self):
        assert estimate_matrix_count(None) == 1
        assert estimate_matrix_count({}) == 1

    def test_all_excluded_returns_empty(self):
        result = generate_matrix_combinations(
            {"os": ["linux"]},
            exclude=[{"os": "linux"}],
        )
        assert result == []

    def test_value_processor_applies_to_combos_filters_and_includes(self):
        def bool_strings(value):
            return value == "true" if value in {"true", "false"} else value

        result = generate_matrix_combinations(
            {"enabled": ["true", "false"]},
            exclude=[{"enabled": "false"}],
            include=[{"enabled": "manual"}],
            value_processor=bool_strings,
        )

        assert result == [{"enabled": True}, {"enabled": "manual"}]

    def test_scalar_matrix_value_is_single_dimension_value(self):
        assert generate_matrix_combinations({"target": "example.com"}) == [
            {"target": "example.com"}
        ]

from ofx.runner.services.credential_store import (
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

        with patch.dict("sys.modules", {"ofx.api.creds.exegol_history": None}):
            result = store_from_typed_outputs([account], log_fn=logs.append)
        assert result == 0
        assert any("unavailable" in m for m in logs)

from ofx.runner.step_descriptors import (
    step_timeline_params,
    step_type_label,
)
from ofx.runner.step_output import log_output, save_output_file


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
        result = save_output_file(tmp_path, "job1", step, "hello world", {})
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

    def test_output_log_helpers_build_path_and_flags(self, tmp_path):
        step = SimpleNamespace(name="scan step", step_index=2)

        result = save_output_file(tmp_path, "job-1", step, "data")

        assert result == tmp_path / "logs" / "stdout_job-1_scan-step.log"
        flagged = save_output_file(
            tmp_path,
            "job-2",
            step,
            "data",
            {"binary_output": True, "stderr_truncated": True},
        )
        assert flagged is not None
        content = flagged.read_text()
        assert "[BINARY OUTPUT]" in content
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

class TestStepDescriptors:
    def test_public_descriptor_helpers_cover_non_command_cases(self, tmp_path):
        task_step = SimpleNamespace(
            task="nmap",
            pipe=None,
            uses=None,
            script=None,
            script_file=None,
            run=None,
        )
        pipe_step = SimpleNamespace(
            pipe=SimpleNamespace(format="yaml"),
            task=None,
            uses=None,
            script=None,
            script_file=None,
            run=None,
        )
        command_step = SimpleNamespace(
            name="command",
            run="echo hi",
            uses=None,
            script_file=None,
            script=None,
            task=None,
            pipe=None,
        )
        script_file_step = SimpleNamespace(
            name="script-file",
            run=None,
            uses=None,
            script_file="worker.py",
            script=None,
            task=None,
            pipe=None,
        )

        assert step_type_label(task_step) == "task: nmap"
        assert step_type_label(pipe_step) == "pipe: → yaml"
        command_log = save_output_file(tmp_path, "job", command_step, "ok")
        script_file_log = save_output_file(tmp_path, "job", script_file_step, "ok")

        assert command_log is not None
        assert script_file_log is not None
        assert command_log.read_text().startswith(">> command: echo hi\n>>===<<\nok")
        assert script_file_log.read_text().startswith(">> script_file: worker.py\n>>===<<\nok")

    def test_step_type_label_for_pipe(self):
        step = SimpleNamespace(pipe=SimpleNamespace(format="yaml"), task=None, uses=None, script=None, script_file=None, run=None)

        assert step_type_label(step) == "pipe: → yaml"

    def test_save_output_file_uses_workflow_header(self, tmp_path):
        step = SimpleNamespace(run=None, uses="./child.yml", script_file=None, script=None, task=None, pipe=None)

        result = save_output_file(tmp_path, "job", step, "ok")

        assert result is not None
        assert result.read_text().startswith(">> workflow: ./child.yml\n>>===<<\nok")

    def test_step_timeline_params_for_task(self):
        step = SimpleNamespace(
            run=None,
            uses=None,
            script_file=None,
            script=None,
            task="nmap",
            pipe=None,
            run_with={"targets": ["a", "b"], "ports": "80"},
            name="scan",
        )

        assert step_timeline_params(step, outputs={}) == {
            "command": "task:nmap",
            "tool": "nmap",
            "target": "a,b",
        }

    def test_step_timeline_params_for_pipe(self):
        step = SimpleNamespace(
            run=None,
            uses=None,
            script_file=None,
            script=None,
            task=None,
            pipe=SimpleNamespace(format="yaml"),
            name="transform",
        )

        assert step_timeline_params(step, outputs={}) == {
            "command": "pipe:transform",
            "tool": "",
            "target": "",
        }

    def test_step_timeline_params_for_workflow_uses_workflow_source_not_step_name(self):
        step = SimpleNamespace(
            run=None,
            uses="./child.yml",
            script_file=None,
            script=None,
            task=None,
            pipe=None,
            name="child-runner",
        )

        assert step_timeline_params(step, outputs={}) == {
            "command": "uses:./child.yml",
            "tool": "",
            "target": "",
        }

    def test_step_timeline_params_for_script_file_uses_script_path_not_step_name(self):
        step = SimpleNamespace(
            run=None,
            uses=None,
            script_file="worker.py",
            script=None,
            task=None,
            pipe=None,
            name="script-step",
        )

        assert step_timeline_params(step, outputs={}) == {
            "command": "script_file:worker.py",
            "tool": "",
            "target": "",
        }

class TestCloudRetryBackoff:
    def test_retry_delay_exponential(self):
        from ofx.runner.cloud_step import CloudStepRunner

        for attempt in range(5):
            delay = CloudStepRunner._retry_delay_seconds(attempt, base_delay=10)
            expected_backoff = 10 * (2**attempt)
            expected_capped = min(expected_backoff, 300)
            assert expected_capped * 0.5 <= delay <= expected_capped * 1.0

    def test_retry_delay_capped_at_300(self):
        from ofx.runner.cloud_step import CloudStepRunner

        delay = CloudStepRunner._retry_delay_seconds(10, base_delay=10)
        assert delay <= 300

    def test_matches_local_step_runner(self):
        from ofx.runner.cloud_step import CloudStepRunner
        from ofx.runner.step import StepRunner

        for attempt in range(5):
            for _ in range(20):
                local = StepRunner._retry_delay_seconds(attempt, 10)
                cloud = CloudStepRunner._retry_delay_seconds(attempt, 10)
                cap = min(10 * (2**attempt), 300)
                assert cap * 0.5 <= local <= cap
                assert cap * 0.5 <= cloud <= cap
