"""Tests for ofx.runner.execution.output_formatter."""

from __future__ import annotations

import io

from rich.console import Console

from ofx.runner.execution.output_formatter import (
    _cell_style,
    _cell_value,
    format_typed_outputs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _capture_console() -> tuple[Console, io.StringIO]:
    """Return a Console that writes to a StringIO buffer."""
    buf = io.StringIO()
    return Console(file=buf, force_terminal=True, width=200), buf


# ---------------------------------------------------------------------------
# TestCellValue
# ---------------------------------------------------------------------------


class TestCellValue:
    """Tests for _cell_value."""

    def test_none_field(self):
        assert _cell_value({"x": None}, "x") == ""

    def test_empty_string(self):
        assert _cell_value({"x": ""}, "x") == ""

    def test_zero_value(self):
        assert _cell_value({"x": 0}, "x") == ""

    def test_normal_string(self):
        assert _cell_value({"x": "hello"}, "x") == "hello"

    def test_normal_int(self):
        assert _cell_value({"port": 443}, "port") == "443"

    def test_list_leq_5(self):
        assert _cell_value({"t": ["a", "b", "c"]}, "t") == "a, b, c"

    def test_list_exactly_5(self):
        items = ["a", "b", "c", "d", "e"]
        assert _cell_value({"t": items}, "t") == "a, b, c, d, e"

    def test_list_gt_5(self):
        items = ["a", "b", "c", "d", "e", "f", "g"]
        result = _cell_value({"t": items}, "t")
        assert result == "a, b, c, d, e…"

    def test_bool_true(self):
        assert _cell_value({"x": True}, "x") == "✓"

    def test_bool_false(self):
        # False == 0 is True in Python, so it hits the val == 0 branch first
        assert _cell_value({"x": False}, "x") == ""

    def test_missing_key(self):
        assert _cell_value({}, "missing") == ""


# ---------------------------------------------------------------------------
# TestCellStyle
# ---------------------------------------------------------------------------


class TestCellStyle:
    """Tests for _cell_style."""

    def test_severity_critical(self):
        assert _cell_style({"severity": "critical"}, "severity", "base") == "bold white on red"

    def test_severity_high(self):
        assert _cell_style({"severity": "high"}, "severity", "base") == "bold red"

    def test_severity_medium(self):
        assert _cell_style({"severity": "Medium"}, "severity", "base") == "yellow"

    def test_severity_low(self):
        assert _cell_style({"severity": "low"}, "severity", "base") == "blue"

    def test_severity_info(self):
        assert _cell_style({"severity": "info"}, "severity", "base") == "dim"

    def test_severity_unknown(self):
        assert _cell_style({"severity": "unknown"}, "severity", "base") == "dim"

    def test_severity_unrecognized_falls_back(self):
        assert _cell_style({"severity": "custom"}, "severity", "base") == "base"

    def test_status_code_200(self):
        assert _cell_style({"status_code": 200}, "status_code", "base") == "green"

    def test_status_code_301(self):
        assert _cell_style({"status_code": 301}, "status_code", "base") == "yellow"

    def test_status_code_404(self):
        assert _cell_style({"status_code": 404}, "status_code", "base") == "red"

    def test_status_code_500(self):
        assert _cell_style({"status_code": 500}, "status_code", "base") == "bold red"

    def test_status_code_zero_returns_base(self):
        assert _cell_style({"status_code": 0}, "status_code", "base") == "base"

    def test_status_code_non_int_returns_base(self):
        assert _cell_style({"status_code": "200"}, "status_code", "base") == "base"

    def test_non_special_field(self):
        assert _cell_style({"host": "example.com"}, "host", "cyan") == "cyan"


# ---------------------------------------------------------------------------
# TestFormatTypedOutputs
# ---------------------------------------------------------------------------


class TestFormatTypedOutputs:
    """Tests for format_typed_outputs."""

    def test_empty_list_no_output(self):
        console, buf = _capture_console()
        format_typed_outputs([], task_name="test", console=console)
        assert buf.getvalue() == ""

    def test_port_items_render_panel(self):
        items = [
            {"_type": "port", "ip": "10.0.0.1", "port": 80, "protocol": "tcp", "state": "open", "service_name": "http"},
            {"_type": "port", "ip": "10.0.0.1", "port": 443, "protocol": "tcp", "state": "open", "service_name": "https"},
        ]
        console, buf = _capture_console()
        format_typed_outputs(items, task_name="nmap", console=console)
        output = buf.getvalue()
        assert "10.0.0.1" in output
        assert "80" in output
        assert "443" in output
        assert "nmap" in output

    def test_unknown_type_shows_count(self):
        items = [
            {"_type": "custom_thing", "data": "abc"},
            {"_type": "custom_thing", "data": "def"},
        ]
        console, buf = _capture_console()
        format_typed_outputs(items, task_name="test", console=console)
        output = buf.getvalue()
        assert "custom_thing" in output
        assert "2 item(s)" in output

    def test_mixed_types_render_multiple_sections(self):
        items = [
            {"_type": "port", "ip": "10.0.0.1", "port": 22, "protocol": "tcp", "state": "open", "service_name": "ssh"},
            {"_type": "url", "url": "https://example.com", "status_code": 200, "title": "Example", "tech": ""},
            {"_type": "mystery", "foo": "bar"},
        ]
        console, buf = _capture_console()
        format_typed_outputs(items, task_name="scan", console=console)
        output = buf.getvalue()
        assert "10.0.0.1" in output
        assert "https://example.com" in output
        assert "mystery" in output
        assert "1 item(s)" in output

    def test_all_empty_fields_skipped(self):
        # Every data field is None/empty/0 — the type should be skipped
        items = [
            {"_type": "port", "ip": None, "port": 0, "protocol": "", "state": None, "service_name": ""},
        ]
        console, buf = _capture_console()
        format_typed_outputs(items, task_name="test", console=console)
        # Nothing renderable → no output
        assert buf.getvalue() == ""

    def test_overflow_more_than_50_items(self):
        items = [
            {"_type": "port", "ip": f"10.0.0.{i % 256}", "port": 8000 + i, "protocol": "tcp", "state": "open", "service_name": "http"}
            for i in range(1, 62)  # 61 items
        ]
        console, buf = _capture_console()
        format_typed_outputs(items, task_name="nmap", console=console)
        output = buf.getvalue()
        assert "+11 more" in output

    def test_summary_counts_displayed(self):
        items = [
            {"_type": "port", "ip": "10.0.0.1", "port": 80, "protocol": "tcp", "state": "open", "service_name": "http"},
            {"_type": "port", "ip": "10.0.0.1", "port": 443, "protocol": "tcp", "state": "open", "service_name": "https"},
            {"_type": "url", "url": "https://a.com", "status_code": 200, "title": "A", "tech": ""},
        ]
        console, buf = _capture_console()
        format_typed_outputs(items, task_name="multi", console=console)
        output = buf.getvalue()
        # Summary shows counts per type
        assert "2" in output
        assert "1" in output

    def test_default_title_when_no_task_name(self):
        items = [
            {"_type": "port", "ip": "10.0.0.1", "port": 22, "protocol": "tcp", "state": "open", "service_name": "ssh"},
        ]
        console, buf = _capture_console()
        format_typed_outputs(items, task_name="", console=console)
        output = buf.getvalue()
        assert "Task Results" in output
