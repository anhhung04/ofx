"""Tests for ofx.runner.timeline."""

from __future__ import annotations

import json
from pathlib import Path

import ofx.runner.timeline as tmod
from ofx.runner.timeline import _format_duration, _resolve_command_log_path, detect_target, log_step


def test_detect_target_flag_h():
    assert detect_target("nmap -h 10.0.0.1 -p 80") == "10.0.0.1"


def test_detect_target_flag_host():
    assert detect_target("tool --host 10.0.0.1") == "10.0.0.1"


def test_detect_target_flag_url():
    assert detect_target("tool --url http://target.com/path") == "target.com"


def test_detect_target_flag_target():
    assert detect_target("nuclei --target example.com") == "example.com"


def test_detect_target_flag_t():
    assert detect_target("nikto -t 192.168.1.5") == "192.168.1.5"


def test_detect_target_flag_u():
    assert detect_target("sqlmap -u http://vuln.app/page") == "vuln.app"


def test_detect_target_flag_d():
    assert detect_target("subfinder -d example.org") == "example.org"


def test_detect_target_url_based():
    assert detect_target("curl https://example.com/path") == "example.com"


def test_detect_target_url_with_port():
    assert detect_target("curl http://host.io:8080/api") == "host.io"


def test_detect_target_ip_based():
    assert detect_target("nmap 192.168.1.1") == "192.168.1.1"


def test_detect_target_cidr():
    assert detect_target("nmap 10.0.0.0/24") == "10.0.0.0/24"


def test_detect_target_skips_loopback():
    assert detect_target("ping 127.0.0.1") == ""


def test_detect_target_skips_zero():
    assert detect_target("something 0.0.0.1") == ""


def test_detect_target_no_target():
    assert detect_target("echo hello") == ""


def test_format_duration_none():
    assert _format_duration(None) == ""


def test_format_duration_seconds():
    assert _format_duration(5400) == "5.4s"


def test_format_duration_minutes():
    assert _format_duration(90000) == "1.5m"


def test_format_duration_hours():
    assert _format_duration(7200000) == "2.0h"


def test_format_duration_boundary_60s():
    assert _format_duration(60000) == "1.0m"


def test_format_duration_boundary_3600s():
    assert _format_duration(3600000) == "1.0h"


def test_format_duration_zero():
    assert _format_duration(0) == "0.0s"


def test_resolve_command_log_path_explicit_file(monkeypatch):
    monkeypatch.setenv("OFX_COMMAND_LOG_FILE", "/tmp/custom.ndjson")
    assert _resolve_command_log_path({"project_name": "proj"}) == Path("/tmp/custom.ndjson")


def test_resolve_command_log_path_project_logs_var(monkeypatch):
    monkeypatch.delenv("OFX_COMMAND_LOG_FILE", raising=False)
    monkeypatch.delenv("OFX_COMMAND_LOG_DIR", raising=False)
    monkeypatch.delenv("OFX_COMMAND_LOG_NAME", raising=False)
    assert _resolve_command_log_path(
        {"project_logs": "/var/logs", "project_name": "pentest1"}
    ) == Path("/var/logs/command_log.ndjson")


def test_resolve_command_log_path_project_path(monkeypatch, tmp_path):
    monkeypatch.delenv("OFX_COMMAND_LOG_FILE", raising=False)
    monkeypatch.delenv("OFX_COMMAND_LOG_NAME", raising=False)
    monkeypatch.delenv("OFX_COMMAND_LOG_DIR", raising=False)
    project_path = tmp_path / "myproject"
    assert _resolve_command_log_path(
        {"project_path": str(project_path), "project_name": "myproject"}
    ) == project_path / "logs" / "command_log.ndjson"


def test_resolve_command_log_path_default(monkeypatch):
    monkeypatch.delenv("OFX_COMMAND_LOG_FILE", raising=False)
    monkeypatch.delenv("OFX_COMMAND_LOG_DIR", raising=False)
    monkeypatch.delenv("OFX_COMMAND_LOG_NAME", raising=False)
    result = _resolve_command_log_path({})
    assert result == Path("~/.ofx/logs/command/default.ndjson").expanduser()


def test_log_step_appends_ndjson(tmp_path, monkeypatch):
    monkeypatch.delenv("OFX_COMMAND_LOG_FILE", raising=False)
    monkeypatch.delenv("OFX_COMMAND_LOG_DIR", raising=False)
    monkeypatch.delenv("OFX_COMMAND_LOG_NAME", raising=False)
    tmod._source_host_cache = ""
    monkeypatch.setenv("OFX_COMMAND_LOG_SOURCE_HOST", "testbox")
    monkeypatch.setenv("OFX_COMMAND_LOG_SOURCE_IP", "1.2.3.4")

    project_path = tmp_path / "demo-project"

    log_step(
        ctx_vars={"project_name": "demo", "project_path": str(project_path)},
        step_name="scan",
        command="nmap 10.0.0.1",
        tool="nmap",
        target="10.0.0.1",
        status="success",
        duration_ms=5000,
    )

    log_file = project_path / "logs" / "command_log.ndjson"
    assert log_file.exists()
    records = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["step_name"] == "scan"
    assert records[0]["command"] == "nmap 10.0.0.1"
    assert records[0]["tool"] == "nmap"
    assert records[0]["target"] == "10.0.0.1"
    assert records[0]["source_host"] == "testbox (1.2.3.4)"
    assert records[0]["project_name"] == "demo"
    assert records[0]["status"] == "success"
    assert records[0]["duration_ms"] == 5000
    assert records[0]["duration"] == "5.0s"
    assert records[0]["exit_code"] is None
    assert records[0]["tags"] == ["ofx", "duration:5.0s", "status:success"]
    assert records[0]["timestamp"].endswith("Z")


def test_log_step_with_exit_code_and_extra_tags(tmp_path, monkeypatch):
    fallback_file = tmp_path / "fallback.ndjson"
    monkeypatch.setenv("OFX_COMMAND_LOG_FILE", str(fallback_file))
    monkeypatch.delenv("OFX_COMMAND_LOG_DIR", raising=False)
    monkeypatch.delenv("OFX_COMMAND_LOG_NAME", raising=False)
    tmod._source_host_cache = ""
    monkeypatch.setenv("OFX_COMMAND_LOG_SOURCE_HOST", "box")
    monkeypatch.setenv("OFX_COMMAND_LOG_SOURCE_IP", "5.5.5.5")

    log_step(
        ctx_vars={},
        step_name="fail-step",
        command="false",
        tool="",
        target="",
        status="failed",
        duration_ms=100,
        exit_code=1,
        tags="cloud;batch:nightly",
    )

    log_file = fallback_file
    assert log_file.exists()
    records = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert records[0]["tags"] == [
        "ofx",
        "duration:0.1s",
        "status:failed",
        "exit:1",
        "cloud",
        "batch:nightly",
    ]
    assert records[0]["target"] == ""
