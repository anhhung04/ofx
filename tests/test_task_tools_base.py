"""Tests for individual tool parsers, parse_line, streaming detection, and output edge cases."""

import json
from pathlib import Path

from ofx.tasks import (
    Task,
    TaskRegistry,
)

# ── Live Streaming (parse_line) ────────────────────────────────────────


class TestParseLine:
    def test_httpx_parse_line(self):
        task = TaskRegistry.create("httpx")
        result = task.parse_line('{"url":"https://example.com","status_code":200}')
        assert len(result) >= 1
        assert result[0]._type == "url"

    def test_httpx_parse_line_empty(self):
        task = TaskRegistry.create("httpx")
        assert task.parse_line("") == []
        assert task.parse_line("not json") == []

    def test_naabu_parse_line(self):
        task = TaskRegistry.create("naabu")
        result = task.parse_line('{"ip":"10.0.0.1","port":22}')
        assert len(result) == 1
        assert result[0]._type == "port"
        assert result[0].port == 22

    def test_nuclei_parse_line(self):
        task = TaskRegistry.create("nuclei")
        line = json.dumps(
            {
                "template-id": "test-vuln",
                "info": {"name": "Test Vuln", "severity": "high", "tags": ["cve"]},
                "matched-at": "https://target.com",
            }
        )
        result = task.parse_line(line)
        assert any(r._type == "vulnerability" for r in result)

    def test_subfinder_parse_line(self):
        task = TaskRegistry.create("subfinder")
        result = task.parse_line("api.example.com")
        assert len(result) == 1
        assert result[0]._type == "subdomain"
        assert result[0].host == "api.example.com"

    def test_katana_parse_line_json(self):
        task = TaskRegistry.create("katana")
        result = task.parse_line('{"request":{"endpoint":"https://x.com/path"}}')
        assert len(result) >= 1

    def test_katana_parse_line_plain_url(self):
        task = TaskRegistry.create("katana")
        result = task.parse_line("https://example.com/page")
        assert len(result) == 1
        assert result[0].url == "https://example.com/page"

    def test_dnsx_parse_line(self):
        task = TaskRegistry.create("dnsx")
        line = json.dumps({"host": "example.com", "a": ["1.2.3.4"]})
        result = task.parse_line(line)
        assert any(r._type == "subdomain" for r in result)

    def test_feroxbuster_parse_line(self):
        task = TaskRegistry.create("feroxbuster")
        line = json.dumps(
            {"type": "response", "url": "https://x.com/admin", "status": 200}
        )
        result = task.parse_line(line)
        assert len(result) == 1
        assert result[0].url == "https://x.com/admin"

    def test_feroxbuster_skip_non_response(self):
        task = TaskRegistry.create("feroxbuster")
        line = json.dumps({"type": "log", "message": "blah"})
        assert task.parse_line(line) == []

    def test_nmap_no_streaming(self):
        task = TaskRegistry.create("nmap")
        assert not task.supports_streaming

    def test_httpx_supports_streaming(self):
        task = TaskRegistry.create("httpx")
        assert task.supports_streaming

    def test_naabu_supports_streaming(self):
        task = TaskRegistry.create("naabu")
        assert task.supports_streaming


# ── Error Scenarios & Edge Cases ───────────────────────────────────────


# ── Error Scenarios & Edge Cases ───────────────────────────────────────


class TestParseLineEdgeCases:
    """Edge cases for parse_line across streaming tools."""

    def test_malformed_json_returns_empty(self):
        from ofx.tasks.tools.httpx import HttpxTask

        task = HttpxTask()
        assert task.parse_line('{"url": "http://test.com", broken') == []

    def test_empty_line_returns_empty(self):
        from ofx.tasks.tools.httpx import HttpxTask

        task = HttpxTask()
        assert task.parse_line("") == []
        assert task.parse_line("   ") == []

    def test_non_json_line_returns_empty(self):
        from ofx.tasks.tools.nuclei import NucleiTask

        task = NucleiTask()
        assert task.parse_line("[INF] Loading templates...") == []

    def test_json_missing_required_fields_returns_empty(self):
        from ofx.tasks.tools.httpx import HttpxTask

        task = HttpxTask()
        # Valid JSON but no url field
        assert task.parse_line('{"status_code": 200}') == []

    def test_naabu_non_json_line(self):
        from ofx.tasks.tools.naabu import NaabuTask

        task = NaabuTask()
        assert task.parse_line("[INF] Running host scan...") == []

    def test_feroxbuster_non_response_line(self):
        from ofx.tasks.tools.feroxbuster import FeroxbusterTask

        task = FeroxbusterTask()
        # Lines without "type":"response" should be skipped
        assert task.parse_line('{"type": "statistics", "data": {}}') == []

    def test_invalid_url_host_is_empty(self):
        task = TaskRegistry.create("feroxbuster")
        line = json.dumps(
            {"type": "response", "url": "http://[::1", "status": 200}
        )

        result = task.parse_line(line)

        assert len(result) == 1
        assert result[0].host == ""

    def test_dnsx_empty_json(self):
        from ofx.tasks.tools.dnsx import DnsxTask

        task = DnsxTask()
        assert task.parse_line("{}") == []


class TestParseOutputEdgeCases:
    """Edge cases for parse_output file/stdout handling."""

    def test_parse_output_nonexistent_file(self):
        from ofx.tasks.tools.httpx import HttpxTask

        task = HttpxTask()
        result = task.parse_output(
            stdout="", stderr="", output_file=Path("/nonexistent/file.jsonl")
        )
        assert result == []

    def test_parse_output_empty_file(self, tmp_path):
        from ofx.tasks.tools.nuclei import NucleiTask

        task = NucleiTask()
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")
        result = task.parse_output(stdout="", stderr="", output_file=empty_file)
        assert result == []

    def test_parse_output_falls_back_to_stdout(self):
        from ofx.tasks.tools.subfinder import SubfinderTask

        task = SubfinderTask()
        result = task.parse_output(
            stdout="sub1.example.com\nsub2.example.com",
            stderr="",
            output_file=None,
        )
        assert len(result) == 2
        assert result[0].host == "sub1.example.com"

    def test_nmap_empty_xml_returns_empty(self, tmp_path):
        from ofx.tasks.tools.nmap import NmapTask

        task = NmapTask()
        empty_file = tmp_path / "empty.xml"
        empty_file.write_text("")
        result = task.parse_output(stdout="", stderr="", output_file=empty_file)
        assert result == []

    def test_nmap_malformed_xml_returns_empty(self, tmp_path):
        from ofx.tasks.tools.nmap import NmapTask

        task = NmapTask()
        bad_file = tmp_path / "bad.xml"
        bad_file.write_text("<nmaprun><host><broken>")
        result = task.parse_output(stdout="", stderr="", output_file=bad_file)
        # Should handle gracefully — either empty or partial results
        assert isinstance(result, list)

    def test_ffuf_empty_json_returns_empty(self, tmp_path):
        from ofx.tasks.tools.ffuf import FfufTask

        task = FfufTask()
        empty_file = tmp_path / "empty.json"
        empty_file.write_text("")
        result = task.parse_output(stdout="", stderr="", output_file=empty_file)
        assert result == []

    def test_ffuf_malformed_json_returns_empty(self, tmp_path):
        from ofx.tasks.tools.ffuf import FfufTask

        task = FfufTask()
        bad_file = tmp_path / "bad.json"
        bad_file.write_text('{"results": [broken')
        result = task.parse_output(stdout="", stderr="", output_file=bad_file)
        assert result == []


class TestReadOutputFile:
    """Tests for Task._read_output_file helper."""

    def test_read_valid_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        assert Task._read_output_file(f) == "hello world"

    def test_read_nonexistent_file(self):
        assert Task._read_output_file(Path("/nonexistent/file.txt")) == ""

    def test_read_binary_file(self, tmp_path):
        f = tmp_path / "binary.bin"
        f.write_bytes(b"\x00\x01\x02\xff")
        result = Task._read_output_file(f)
        assert isinstance(result, str)


class TestStreamingDetectionEdgeCases:
    """Additional streaming detection tests."""

    def test_base_task_no_streaming(self):
        """Concrete task with no parse_line override → no streaming."""

        class PlainTask(Task):
            name = "plain"
            cmd = "plain"

            def parse_output(self, stdout, stderr, output_file=None):
                return []

        task = PlainTask()
        assert not task.supports_streaming

    def test_task_with_parse_line_supports_streaming(self):
        """Task with parse_line override → streaming."""

        class StreamTask(Task):
            name = "stream"
            cmd = "stream"

            def parse_output(self, stdout, stderr, output_file=None):
                return []

            def parse_line(self, line):
                return []

        task = StreamTask()
        assert task.supports_streaming


# ── Gospider Parser ────────────────────────────────────────────────────
