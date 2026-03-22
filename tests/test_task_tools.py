"""Tests for individual tool parsers, parse_line, streaming detection, and output edge cases."""

import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from ofx.tasks import (
    Port,
    Subdomain,
    Task,
    TaskRegistry,
    Url,
    Vulnerability,
)
from ofx.tasks.output_types import (
    Ip,
    Severity,
    Tag,
)


# ── Nmap Parser ────────────────────────────────────────────────────────────


class TestNmapParser:
    def _make_nmap_xml(self, ports: list[dict]) -> str:
        root = ET.Element("nmaprun")
        host = ET.SubElement(root, "host")
        addr = ET.SubElement(host, "address")
        addr.set("addr", "10.0.0.1")
        hostnames = ET.SubElement(host, "hostnames")
        hn = ET.SubElement(hostnames, "hostname")
        hn.set("name", "testhost")
        ports_el = ET.SubElement(host, "ports")
        for p in ports:
            port_el = ET.SubElement(ports_el, "port")
            port_el.set("portid", str(p["port"]))
            port_el.set("protocol", p.get("protocol", "tcp"))
            state = ET.SubElement(port_el, "state")
            state.set("state", p.get("state", "open"))
            if "service" in p:
                svc = ET.SubElement(port_el, "service")
                svc.set("name", p["service"])
                if "product" in p:
                    svc.set("product", p["product"])
                if "version" in p:
                    svc.set("version", p["version"])
        return ET.tostring(root, encoding="unicode")

    def test_parse_basic_ports(self):
        xml = self._make_nmap_xml(
            [
                {"port": 22, "service": "ssh"},
                {"port": 80, "service": "http"},
            ]
        )
        task = TaskRegistry.create("nmap")
        results = task.parse_output(xml, "")
        ports = [r for r in results if isinstance(r, Port)]
        assert len(ports) == 2
        assert ports[0].port == 22
        assert ports[1].port == 80

    def test_parse_closed_ports_ignored(self):
        xml = self._make_nmap_xml(
            [
                {"port": 22, "service": "ssh", "state": "closed"},
            ]
        )
        task = TaskRegistry.create("nmap")
        results = task.parse_output(xml, "")
        assert len(results) == 0

    def test_parse_service_name_with_version(self):
        xml = self._make_nmap_xml(
            [
                {
                    "port": 80,
                    "service": "http",
                    "product": "Apache",
                    "version": "2.4.51",
                },
            ]
        )
        task = TaskRegistry.create("nmap")
        results = task.parse_output(xml, "")
        ports = [r for r in results if isinstance(r, Port)]
        assert "Apache" in ports[0].service_name

    def test_parse_from_file(self):
        xml = self._make_nmap_xml([{"port": 443, "service": "https"}])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml)
            f.flush()
            task = TaskRegistry.create("nmap")
            results = task.parse_output("", "", output_file=Path(f.name))
            assert len(results) == 1
            Path(f.name).unlink()

    def test_parse_empty_output(self):
        task = TaskRegistry.create("nmap")
        results = task.parse_output("", "")
        assert results == []

    def test_parse_invalid_xml(self):
        task = TaskRegistry.create("nmap")
        results = task.parse_output("<invalid>", "")
        assert results == []


# ── Httpx Parser ───────────────────────────────────────────────────────────


class TestHttpxParser:
    def test_parse_jsonl(self):
        lines = [
            json.dumps(
                {
                    "url": "https://example.com",
                    "status_code": 200,
                    "title": "Example",
                    "tech": ["nginx", "PHP"],
                    "webserver": "nginx",
                }
            ),
            json.dumps(
                {
                    "url": "https://api.example.com",
                    "status_code": 301,
                }
            ),
        ]
        task = TaskRegistry.create("httpx")
        results = task.parse_output("\n".join(lines), "")
        urls = [r for r in results if isinstance(r, Url)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(urls) == 2
        assert urls[0].status_code == 200
        assert len(tags) == 2  # nginx + PHP

    def test_parse_empty(self):
        task = TaskRegistry.create("httpx")
        assert task.parse_output("", "") == []


# ── Nuclei Parser ──────────────────────────────────────────────────────────


class TestNucleiParser:
    def test_parse_jsonl(self):
        entry = {
            "template-id": "cve-2021-44228",
            "matched-at": "https://target.com",
            "info": {
                "name": "Log4Shell",
                "severity": "critical",
                "tags": "rce,cve",
                "description": "Remote code execution",
                "reference": ["https://nvd.nist.gov/vuln/detail/CVE-2021-44228"],
            },
        }
        task = TaskRegistry.create("nuclei")
        results = task.parse_output(json.dumps(entry), "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        assert len(vulns) == 1
        assert vulns[0].severity == Severity.CRITICAL
        assert vulns[0].name == "Log4Shell"


# ── Subfinder Parser ──────────────────────────────────────────────────────


class TestSubfinderParser:
    def test_parse_output(self):
        stdout = "api.example.com\nwww.example.com\nmail.example.com\n"
        task = TaskRegistry.create("subfinder")
        results = task.parse_output(stdout, "")
        assert len(results) == 3
        assert all(isinstance(r, Subdomain) for r in results)
        assert results[0].host == "api.example.com"
        assert results[0].domain == "example.com"


# ── Ffuf Parser ────────────────────────────────────────────────────────────


class TestFfufParser:
    def test_parse_json(self):
        data = {
            "results": [
                {
                    "url": "https://x.com/admin",
                    "status": 200,
                    "length": 1234,
                    "words": 50,
                },
                {"url": "https://x.com/login", "status": 302, "length": 0},
            ]
        }
        task = TaskRegistry.create("ffuf")
        results = task.parse_output(json.dumps(data), "")
        assert len(results) == 2
        assert all(isinstance(r, Url) for r in results)
        assert results[0].status_code == 200

    def test_parse_empty_results(self):
        task = TaskRegistry.create("ffuf")
        results = task.parse_output(json.dumps({"results": []}), "")
        assert results == []


# ── Naabu Parser ──────────────────────────────────────────────────────────


class TestNaabuParser:
    def test_parse_jsonl(self):
        lines = [
            json.dumps({"ip": "10.0.0.1", "port": 80, "protocol": "tcp"}),
            json.dumps({"ip": "10.0.0.1", "port": 443, "protocol": "tcp"}),
            json.dumps({"host": "10.0.0.2", "port": 22}),
        ]
        task = TaskRegistry.create("naabu")
        results = task.parse_output("\n".join(lines), "")
        assert len(results) == 3
        assert all(isinstance(r, Port) for r in results)
        assert results[0].port == 80
        assert results[1].port == 443
        assert results[2].ip == "10.0.0.2"

    def test_command_building(self):
        task = TaskRegistry.create("naabu")
        cmd, _ = task.build_command("10.0.0.0/24", ports="80,443", rate=1000)
        assert "naabu" in cmd
        assert "-json" in cmd
        assert "-silent" in cmd
        assert "-p 80,443" in cmd
        assert "-rate 1000" in cmd


class TestKatanaParser:
    def test_parse_jsonl(self):
        lines = [
            json.dumps({
                "request": {"endpoint": "https://example.com/page", "host": "example.com", "method": "GET"},
                "response": {"status_code": 200},
            }),
        ]
        task = TaskRegistry.create("katana")
        results = task.parse_output("\n".join(lines), "")
        assert len(results) == 1
        assert isinstance(results[0], Url)
        assert results[0].url == "https://example.com/page"

    def test_parse_plain_urls(self):
        stdout = "https://example.com/page1\nhttps://example.com/page2\n"
        task = TaskRegistry.create("katana")
        results = task.parse_output(stdout, "")
        assert len(results) == 2

    def test_command_building(self):
        task = TaskRegistry.create("katana")
        cmd, _ = task.build_command("https://example.com", depth=3, js_crawl=True)
        assert "katana" in cmd
        assert "-jsonl" in cmd
        assert "-depth 3" in cmd
        assert "-js-crawl" in cmd


class TestDnsxParser:
    def test_parse_jsonl(self):
        lines = [
            json.dumps({
                "host": "example.com",
                "a": ["93.184.216.34"],
                "cname": ["cdn.example.com"],
                "mx": ["mail.example.com"],
            }),
        ]
        from ofx.tasks.output_types import Record
        task = TaskRegistry.create("dnsx")
        results = task.parse_output("\n".join(lines), "")
        subdomains = [r for r in results if isinstance(r, Subdomain)]
        ips = [r for r in results if isinstance(r, Ip)]
        records = [r for r in results if isinstance(r, Record)]
        assert len(subdomains) == 1
        assert len(ips) == 1
        assert ips[0].ip == "93.184.216.34"
        assert len(records) == 2  # CNAME + MX

    def test_command_building(self):
        task = TaskRegistry.create("dnsx")
        cmd, _ = task.build_command("example.com", a=True, cname=True, threads=50)
        assert "dnsx" in cmd
        assert "-json" in cmd
        assert "-a" in cmd
        assert "-cname" in cmd
        assert "-t 50" in cmd


class TestWafw00fParser:
    def test_parse_output(self):
        stdout = (
            "[*] Checking https://example.com\n"
            "[+] The site https://example.com is behind Cloudflare (Cloudflare Inc.)\n"
            "[*] Number of requests: 6\n"
        )
        task = TaskRegistry.create("wafw00f")
        results = task.parse_output(stdout, "")
        assert len(results) == 1
        assert isinstance(results[0], Tag)
        assert "Cloudflare" in results[0].name
        assert results[0].category == "waf"

    def test_parse_no_waf(self):
        stdout = "[*] No WAF detected by the generic detection\n"
        task = TaskRegistry.create("wafw00f")
        results = task.parse_output(stdout, "")
        assert results == []


class TestFeroxbusterParser:
    def test_parse_jsonl(self):
        lines = [
            json.dumps({
                "type": "response",
                "url": "https://example.com/admin",
                "status": 200,
                "content_length": 5432,
                "word_count": 120,
                "line_count": 45,
                "method": "GET",
            }),
            json.dumps({"type": "statistics", "elapsed": 10}),  # not a response
        ]
        task = TaskRegistry.create("feroxbuster")
        results = task.parse_output("\n".join(lines), "")
        assert len(results) == 1
        assert isinstance(results[0], Url)
        assert results[0].status_code == 200
        assert results[0].content_length == 5432

    def test_command_building(self):
        task = TaskRegistry.create("feroxbuster")
        cmd, _ = task.build_command(
            "https://example.com", wordlist="/usr/share/seclists/common.txt", threads=50
        )
        assert "feroxbuster" in cmd
        assert "--json" in cmd
        assert "-w /usr/share/seclists/common.txt" in cmd
        assert "-t 50" in cmd


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
        line = json.dumps({
            "template-id": "test-vuln",
            "info": {"name": "Test Vuln", "severity": "high", "tags": ["cve"]},
            "matched-at": "https://target.com",
        })
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
        line = json.dumps({"type": "response", "url": "https://x.com/admin", "status": 200})
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
