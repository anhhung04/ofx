"""Tests for ofx.runner.error_helpers."""

from __future__ import annotations

from ofx.runner.error_helpers import (
    extract_root_error,
    job_failure_summary,
    job_step_failed,
    step_execution_error,
    step_retry_error,
    step_timeout_error,
)

def test_step_execution_error_basic():
    result = step_execution_error(1, "segfault")
    assert result == "Step execution failed with status: 1, error: segfault"

def test_step_execution_error_none_status():
    result = step_execution_error(None, "oops")
    assert "None" in result
    assert "oops" in result

def test_step_timeout_error_includes_timeout():
    result = step_timeout_error(5)
    assert "5 minute(s)" in result

def test_step_timeout_error_suggests_doubled():
    result = step_timeout_error(10)
    assert "timeout: 20" in result

def test_step_retry_error_format():
    result = step_retry_error(3, "connection refused")
    assert "3 attempt(s)" in result
    assert "connection refused" in result

def test_job_step_failed_with_name():
    result = job_step_failed("install-deps", "exit code 1")
    assert result == "Step 'install-deps' failed: exit code 1"

def test_job_step_failed_with_index():
    result = job_step_failed(0, "timeout")
    assert result == "Step '0' failed: timeout"

def test_extract_root_error_none():
    assert extract_root_error(None) == "Unknown error"

def test_extract_root_error_empty():
    assert extract_root_error("") == "Unknown error"

def test_extract_root_error_single_line():
    assert extract_root_error("disk full") == "disk full"

def test_extract_root_error_multiline_returns_deepest():
    error = "Job failure in 'scan':\n====\nStep 'nmap' failed: connection refused"
    assert extract_root_error(error) == "Step 'nmap' failed: connection refused"

def test_extract_root_error_all_wrapper_lines():
    error = "Job failure in 'a':\n===="
    result = extract_root_error(error)
    assert result == "===="

def test_extract_root_error_whitespace_only_lines_skipped():
    error = "Job failure in 'x':\n   \n====\nactual error here"
    assert extract_root_error(error) == "actual error here"

def test_job_failure_summary_basic():
    result = job_failure_summary("deploy", "network timeout")
    assert result == "  job 'deploy': network timeout"

def test_job_failure_summary_none_error():
    result = job_failure_summary("build", None)
    assert "Unknown error" in result

def test_job_failure_summary_extracts_root():
    nested = "Job failure in 'scan':\n====\nconnection refused"
    result = job_failure_summary("scan", nested)
    assert result == "  job 'scan': connection refused"
