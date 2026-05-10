"""Tests for ofx.runner.execution.timeline."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import ofx.runner.execution.timeline as tmod
from ofx.runner.execution.timeline import (
    _csv_row,
    _format_duration,
    _resolve_oops_csv,
    detect_target,
    log_step,
)

# ── detect_target ────────────────────────────────────────────────────────


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


# ── _format_duration ─────────────────────────────────────────────────────


def test_format_duration_none():
    assert _format_duration(None) == ""


def test_format_duration_seconds():
    assert _format_duration(5400) == "5.4s"


def test_format_duration_minutes():
    # 90000 ms = 90s = 1.5m
    assert _format_duration(90000) == "1.5m"


def test_format_duration_hours():
    # 7200000 ms = 7200s = 2.0h
    assert _format_duration(7200000) == "2.0h"


def test_format_duration_boundary_60s():
    # Exactly 60000 ms = 60s = 1.0m
    assert _format_duration(60000) == "1.0m"


def test_format_duration_boundary_3600s():
    # Exactly 3600000 ms = 3600s = 1.0h
    assert _format_duration(3600000) == "1.0h"


def test_format_duration_zero():
    assert _format_duration(0) == "0.0s"


# ── _resolve_oops_csv ───────────────────────────────────────────────────


def test_resolve_oops_csv_explicit_file(monkeypatch):
    monkeypatch.setenv("OOPS_LOG_FILE", "/tmp/custom.csv")
    assert _resolve_oops_csv("proj") == Path("/tmp/custom.csv")


def test_resolve_oops_csv_dir_and_engagement(monkeypatch):
    monkeypatch.delenv("OOPS_LOG_FILE", raising=False)
    monkeypatch.setenv("OOPS_LOG_DIR", "/var/logs")
    monkeypatch.setenv("OOPS_ENGAGEMENT", "pentest1")
    assert _resolve_oops_csv("") == Path("/var/logs/pentest1.csv")


def test_resolve_oops_csv_project_name(monkeypatch):
    monkeypatch.delenv("OOPS_LOG_FILE", raising=False)
    monkeypatch.delenv("OOPS_ENGAGEMENT", raising=False)
    monkeypatch.setenv("OOPS_LOG_DIR", "/var/logs")
    assert _resolve_oops_csv("myproject") == Path("/var/logs/myproject.csv")


def test_resolve_oops_csv_default(monkeypatch):
    monkeypatch.delenv("OOPS_LOG_FILE", raising=False)
    monkeypatch.delenv("OOPS_LOG_DIR", raising=False)
    monkeypatch.delenv("OOPS_ENGAGEMENT", raising=False)
    result = _resolve_oops_csv("")
    assert result == Path("~/.oops/logs/default.csv").expanduser()


# ── _csv_row ─────────────────────────────────────────────────────────────


def test_csv_row_simple():
    row = _csv_row(["a", "b", "c"])
    assert row.strip() == "a,b,c"


def test_csv_row_value_with_comma():
    row = _csv_row(["hello, world", "b"])
    reader = csv.reader(io.StringIO(row))
    parsed = next(reader)
    assert parsed == ["hello, world", "b"]


def test_csv_row_value_with_quotes():
    row = _csv_row(['say "hi"', "ok"])
    reader = csv.reader(io.StringIO(row))
    parsed = next(reader)
    assert parsed == ['say "hi"', "ok"]


def test_csv_row_ends_with_newline():
    row = _csv_row(["x"])
    assert row.endswith("\n")


# ── log_step (integration) ──────────────────────────────────────────────


def test_log_step_appends_csv(tmp_path, monkeypatch):
    monkeypatch.delenv("OOPS_LOG_FILE", raising=False)
    monkeypatch.setenv("OOPS_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("OOPS_ENGAGEMENT", raising=False)
    tmod._source_host_cache = ""
    monkeypatch.setenv("OOPS_SOURCE_HOST", "testbox")
    monkeypatch.setenv("OOPS_SOURCE_IP", "1.2.3.4")

    log_step(
        ctx_vars={"project_name": "demo"},
        output_path=None,
        step_name="scan",
        command="nmap 10.0.0.1",
        tool="nmap",
        target="10.0.0.1",
        status="success",
        duration_ms=5000,
    )

    csv_file = tmp_path / "demo.csv"
    assert csv_file.exists()
    lines = csv_file.read_text().splitlines()
    # First line is header, second is data
    assert len(lines) == 2
    reader = csv.reader(io.StringIO(lines[1]))
    row = next(reader)
    assert row[0] == "[nmap] nmap 10.0.0.1"  # title
    assert row[1] == "nmap 10.0.0.1"  # command
    assert row[2] == "nmap"  # tool
    assert row[5] == "10.0.0.1"  # target


def test_log_step_with_exit_code(tmp_path, monkeypatch):
    monkeypatch.delenv("OOPS_LOG_FILE", raising=False)
    monkeypatch.setenv("OOPS_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("OOPS_ENGAGEMENT", raising=False)
    tmod._source_host_cache = ""
    monkeypatch.setenv("OOPS_SOURCE_HOST", "box")
    monkeypatch.setenv("OOPS_SOURCE_IP", "5.5.5.5")

    log_step(
        ctx_vars={},
        output_path=None,
        step_name="fail-step",
        command="false",
        tool="",
        target="",
        status="failed",
        duration_ms=100,
        exit_code=1,
    )

    csv_file = tmp_path / "default.csv"
    assert csv_file.exists()
    content = csv_file.read_text()
    assert "exit:1" in content
