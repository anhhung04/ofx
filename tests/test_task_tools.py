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


# ── Gospider Parser ────────────────────────────────────────────────────


class TestGospiderParser:
    def test_parse_output(self):
        lines = [
            json.dumps({"output": "https://example.com/page", "source": "sitemap", "type": "url"}),
            json.dumps({"output": "https://example.com/robots.txt", "source": "robots", "type": "url"}),
        ]
        task = TaskRegistry.create("gospider")
        results = task.parse_output("\n".join(lines), "")
        urls = [r for r in results if isinstance(r, Url)]
        assert len(urls) == 2
        assert urls[0].url == "https://example.com/page"
        assert urls[0].host == "example.com"
        assert urls[1].url == "https://example.com/robots.txt"

    def test_parse_output_empty(self):
        task = TaskRegistry.create("gospider")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("gospider")
        cmd, _ = task.build_command("https://example.com", depth=3, threads=10)
        assert "gospider" in cmd
        assert "--json" in cmd
        assert "-q" in cmd
        assert "-s https://example.com" in cmd
        assert "-d 3" in cmd
        assert "-t 10" in cmd

    def test_registration(self):
        task = TaskRegistry.create("gospider")
        assert task.name == "gospider"


# ── Gau Parser ─────────────────────────────────────────────────────────


class TestGauParser:
    def test_parse_output(self):
        lines = [
            json.dumps({"url": "https://example.com/login", "status": 200}),
            json.dumps({"url": "https://example.com/api", "status": 301}),
        ]
        task = TaskRegistry.create("gau")
        results = task.parse_output("\n".join(lines), "")
        urls = [r for r in results if isinstance(r, Url)]
        subs = [r for r in results if isinstance(r, Subdomain)]
        assert len(urls) == 2
        assert urls[0].url == "https://example.com/login"
        assert urls[0].status_code == 200
        assert len(subs) == 2
        assert subs[0].host == "example.com"

    def test_parse_output_empty(self):
        task = TaskRegistry.create("gau")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("gau")
        cmd, _ = task.build_command("example.com", threads=5)
        assert "gau" in cmd
        assert "--json" in cmd
        assert "-t 5" in cmd
        assert "example.com" in cmd

    def test_registration(self):
        task = TaskRegistry.create("gau")
        assert task.name == "gau"


# ── Dalfox Parser ──────────────────────────────────────────────────────


class TestDalfoxParser:
    def test_parse_output(self):
        lines = [
            json.dumps({
                "type": "vuln",
                "data": "[POC] reflected XSS found",
                "proof": "<script>alert(1)</script>",
                "param": "q",
                "payload": "<script>alert(1)</script>",
                "method": "GET",
                "url": "https://example.com/search?q=test",
            }),
        ]
        task = TaskRegistry.create("dalfox")
        results = task.parse_output("\n".join(lines), "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        assert len(vulns) == 1
        assert vulns[0].name == "[POC] reflected XSS found"
        assert vulns[0].provider == "dalfox"
        assert "xss" in vulns[0].tags

    def test_parse_output_non_vuln(self):
        lines = [
            json.dumps({"type": "info", "url": "https://example.com/search"}),
        ]
        task = TaskRegistry.create("dalfox")
        results = task.parse_output("\n".join(lines), "")
        urls = [r for r in results if isinstance(r, Url)]
        assert len(urls) == 1
        assert urls[0].url == "https://example.com/search"

    def test_parse_output_empty(self):
        task = TaskRegistry.create("dalfox")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("dalfox")
        cmd, _ = task.build_command("https://example.com/search?q=test", workers=10)
        assert "dalfox" in cmd
        assert "url" in cmd
        assert "--format" in cmd
        assert "jsonl" in cmd
        assert "-w 10" in cmd
        assert "https://example.com/search?q=test" in cmd

    def test_registration(self):
        task = TaskRegistry.create("dalfox")
        assert task.name == "dalfox"


# ── Maigret Parser ─────────────────────────────────────────────────────


class TestMaigretParser:
    def test_parse_output(self):
        lines = [
            json.dumps({
                "siteName": "GitHub",
                "url_user": "https://github.com/testuser",
                "status": "Claimed",
                "username": "testuser",
            }),
        ]
        task = TaskRegistry.create("maigret")
        results = task.parse_output("\n".join(lines), "")
        from ofx.tasks.output_types import UserAccount
        accounts = [r for r in results if isinstance(r, UserAccount)]
        assert len(accounts) == 1
        assert accounts[0].username == "testuser"
        assert accounts[0].source == "GitHub"
        assert accounts[0].extra_data["url"] == "https://github.com/testuser"

    def test_parse_output_empty(self):
        task = TaskRegistry.create("maigret")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("maigret")
        cmd, _ = task.build_command("testuser", timeout=30)
        assert "maigret" in cmd
        assert "--json" in cmd
        assert "--timeout 30" in cmd
        assert "testuser" in cmd

    def test_registration(self):
        task = TaskRegistry.create("maigret")
        assert task.name == "maigret"


# ── Searchsploit Parser ───────────────────────────────────────────────


class TestSearchsploitParser:
    def test_parse_output(self):
        data = {
            "RESULTS_EXPLOIT": [
                {
                    "Title": "Apache 2.4.49 - Path Traversal",
                    "EDB-ID": "50383",
                    "Platform": "linux",
                    "Type": "webapps",
                },
            ]
        }
        task = TaskRegistry.create("searchsploit")
        results = task.parse_output(json.dumps(data), "")
        from ofx.tasks.output_types import Exploit
        exploits = [r for r in results if isinstance(r, Exploit)]
        assert len(exploits) == 1
        assert exploits[0].name == "Apache 2.4.49 - Path Traversal"
        assert exploits[0].id == "50383"
        assert exploits[0].provider == "exploit-db"
        assert "linux" in exploits[0].tags
        assert "webapps" in exploits[0].tags
        assert "50383" in exploits[0].reference

    def test_parse_output_empty(self):
        task = TaskRegistry.create("searchsploit")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("searchsploit")
        cmd, _ = task.build_command("apache 2.4", exact=True)
        assert "searchsploit" in cmd
        assert "--json" in cmd
        assert "--exact" in cmd
        assert "apache 2.4" in cmd

    def test_registration(self):
        task = TaskRegistry.create("searchsploit")
        assert task.name == "searchsploit"


# ── Gitleaks Parser ────────────────────────────────────────────────────


class TestGitleaksParser:
    def test_parse_output(self, tmp_path):
        findings = [
            {
                "RuleID": "generic-api-key",
                "File": "config.py",
                "StartLine": 15,
                "Commit": "abc123",
                "Author": "dev@test.com",
                "Secret": "AKIAIOSFODNN7EXAMPLE",
            },
        ]
        outfile = tmp_path / "gitleaks.json"
        outfile.write_text(json.dumps(findings))
        task = TaskRegistry.create("gitleaks")
        results = task.parse_output("", "", output_file=outfile)
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(tags) == 1
        assert tags[0].name == "secret"
        assert tags[0].value == "generic-api-key"
        assert tags[0].match == "config.py"
        assert tags[0].category == "secret"
        assert tags[0].extra_data["commit"] == "abc123"
        assert tags[0].extra_data["author"] == "dev@test.com"

    def test_parse_output_empty(self):
        task = TaskRegistry.create("gitleaks")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("gitleaks")
        cmd, _ = task.build_command("/path/to/repo", verbose=True)
        assert "gitleaks" in cmd
        assert "detect" in cmd
        assert "-f json" in cmd
        assert "--source /path/to/repo" in cmd
        assert "-v" in cmd

    def test_registration(self):
        task = TaskRegistry.create("gitleaks")
        assert task.name == "gitleaks"


# ── Trufflehog Parser ─────────────────────────────────────────────────


class TestTrufflehogParser:
    def test_parse_output(self):
        lines = [
            json.dumps({
                "DetectorName": "AWS",
                "Verified": True,
                "Raw": "AKIAIOSFODNN7EXAMPLE",
                "SourceMetadata": {
                    "Data": {"Filesystem": {"file": "secrets.txt"}},
                },
            }),
        ]
        task = TaskRegistry.create("trufflehog")
        results = task.parse_output("\n".join(lines), "")
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(tags) == 1
        assert tags[0].name == "secret"
        assert tags[0].value == "AWS"
        assert tags[0].match == "secrets.txt"
        assert tags[0].extra_data["verified"] is True

    def test_parse_output_empty(self):
        task = TaskRegistry.create("trufflehog")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("trufflehog")
        cmd, _ = task.build_command("https://github.com/org/repo", verified_only=True)
        assert "trufflehog" in cmd
        assert "git" in cmd.split()
        assert "--json" in cmd
        assert "--only-verified" in cmd
        assert "https://github.com/org/repo" in cmd

    def test_registration(self):
        task = TaskRegistry.create("trufflehog")
        assert task.name == "trufflehog"


# ── Grype Parser ───────────────────────────────────────────────────────


class TestGrypeParser:
    def test_parse_output(self):
        data = {
            "matches": [
                {
                    "vulnerability": {
                        "id": "CVE-2021-44228",
                        "severity": "Critical",
                        "fix": {"versions": ["2.17.0"]},
                    },
                    "artifact": {"name": "log4j-core", "version": "2.14.1"},
                },
            ]
        }
        task = TaskRegistry.create("grype")
        results = task.parse_output(json.dumps(data), "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        assert len(vulns) == 1
        assert vulns[0].name == "CVE-2021-44228"
        assert vulns[0].id == "CVE-2021-44228"
        assert vulns[0].severity == Severity.CRITICAL
        assert vulns[0].provider == "grype"
        assert vulns[0].extra_data["package"] == "log4j-core"
        assert vulns[0].extra_data["version"] == "2.14.1"
        assert "2.17.0" in vulns[0].extra_data["fix_versions"]

    def test_parse_output_empty(self):
        task = TaskRegistry.create("grype")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("grype")
        cmd, _ = task.build_command("alpine:3.16", only_fixed=True)
        assert "grype" in cmd
        assert "-o json" in cmd
        assert "--only-fixed" in cmd
        assert "alpine:3.16" in cmd

    def test_registration(self):
        task = TaskRegistry.create("grype")
        assert task.name == "grype"


# ── Trivy Parser ───────────────────────────────────────────────────────


class TestTrivyParser:
    def test_parse_output(self):
        data = {
            "Results": [
                {
                    "Target": "app",
                    "Class": "os-pkgs",
                    "Type": "debian",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2023-1234",
                            "Severity": "HIGH",
                            "PkgName": "openssl",
                            "InstalledVersion": "1.1.1",
                            "FixedVersion": "1.1.2",
                        },
                    ],
                }
            ]
        }
        task = TaskRegistry.create("trivy")
        results = task.parse_output(json.dumps(data), "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(vulns) == 1
        assert vulns[0].name == "CVE-2023-1234"
        assert vulns[0].severity == Severity.HIGH
        assert vulns[0].matched_at == "openssl"
        assert vulns[0].provider == "trivy"
        assert vulns[0].extra_data["installed"] == "1.1.1"
        assert vulns[0].extra_data["fixed"] == "1.1.2"
        assert len(tags) == 1
        assert tags[0].name == "os-pkgs"
        assert tags[0].value == "debian"

    def test_parse_output_empty(self):
        task = TaskRegistry.create("trivy")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("trivy")
        cmd, _ = task.build_command("alpine:3.16", severity="HIGH,CRITICAL")
        assert "trivy" in cmd
        assert "image" in cmd.split()
        assert "-f json" in cmd
        assert "--severity HIGH,CRITICAL" in cmd
        assert "alpine:3.16" in cmd

    def test_registration(self):
        task = TaskRegistry.create("trivy")
        assert task.name == "trivy"


# ── WPScan Parser ─────────────────────────────────────────────────────


class TestWpscanParser:
    def test_parse_output(self):
        data = {
            "plugins": {
                "contact-form-7": {
                    "slug": "contact-form-7",
                    "version": {"number": "5.1"},
                    "vulnerabilities": [
                        {
                            "title": "CF7 < 5.3 - Unrestricted File Upload",
                            "references": {
                                "cve": ["2020-35489"],
                                "wpvulndb": ["10034"],
                            },
                        },
                    ],
                }
            },
            "target_url": "https://example.com",
        }
        task = TaskRegistry.create("wpscan")
        results = task.parse_output(json.dumps(data), "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(vulns) == 1
        assert vulns[0].name == "CF7 < 5.3 - Unrestricted File Upload"
        assert vulns[0].id == "2020-35489"
        assert vulns[0].provider == "wpscan"
        assert len(tags) == 1
        assert tags[0].name == "contact-form-7"
        assert tags[0].value == "5.1"
        assert tags[0].category == "wordpress"

    def test_parse_output_empty(self):
        task = TaskRegistry.create("wpscan")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("wpscan")
        cmd, _ = task.build_command("https://example.com", enumerate="vp,vt", stealthy=True)
        assert "wpscan" in cmd
        assert "--format" in cmd
        assert "json" in cmd
        assert "--url https://example.com" in cmd
        assert "-e vp,vt" in cmd
        assert "--stealthy" in cmd

    def test_registration(self):
        task = TaskRegistry.create("wpscan")
        assert task.name == "wpscan"


# ── SSH-Audit Parser ──────────────────────────────────────────────────


class TestSshAuditParser:
    def test_parse_output(self):
        data = {
            "banner": {"raw": "SSH-2.0-OpenSSH_8.2p1"},
            "cves": [{"name": "CVE-2021-41617", "cvssv2": 7.0}],
            "enc": [
                {"algorithm": "aes128-ctr", "notes": {"warn": ["using weak cipher"]}},
            ],
        }
        task = TaskRegistry.create("ssh-audit")
        results = task.parse_output(json.dumps(data), "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(vulns) == 1
        assert vulns[0].name == "CVE-2021-41617"
        assert vulns[0].severity == Severity.HIGH
        assert vulns[0].provider == "ssh-audit"
        assert vulns[0].cvss_score == 7.0
        # One weak algo tag + one banner tag
        weak_tags = [t for t in tags if t.value == "weak"]
        banner_tags = [t for t in tags if t.category == "banner"]
        assert len(weak_tags) == 1
        assert weak_tags[0].name == "aes128-ctr"
        assert len(banner_tags) == 1
        assert banner_tags[0].value == "SSH-2.0-OpenSSH_8.2p1"

    def test_parse_output_empty(self):
        task = TaskRegistry.create("ssh-audit")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("ssh-audit")
        cmd, _ = task.build_command("192.168.1.1", port=2222)
        assert "ssh-audit" in cmd
        assert "-j" in cmd
        assert "-p 2222" in cmd
        assert "192.168.1.1" in cmd

    def test_registration(self):
        task = TaskRegistry.create("ssh-audit")
        assert task.name == "ssh-audit"


# ── Dirsearch Parser ──────────────────────────────────────────────────


class TestDirsearchParser:
    def test_parse_output(self, tmp_path):
        data = {
            "results": [
                {
                    "url": "https://example.com/admin",
                    "status": 200,
                    "content-length": 1234,
                    "content-type": "text/html",
                    "redirect": "",
                },
            ]
        }
        outfile = tmp_path / "dirsearch.json"
        outfile.write_text(json.dumps(data))
        task = TaskRegistry.create("dirsearch")
        results = task.parse_output("", "", output_file=outfile)
        urls = [r for r in results if isinstance(r, Url)]
        assert len(urls) == 1
        assert urls[0].url == "https://example.com/admin"
        assert urls[0].status_code == 200
        assert urls[0].content_length == 1234
        assert urls[0].content_type == "text/html"

    def test_parse_output_empty(self):
        task = TaskRegistry.create("dirsearch")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("dirsearch")
        cmd, _ = task.build_command("https://example.com", extensions="php,html", threads=30)
        assert "dirsearch" in cmd
        assert "--format" in cmd
        assert "json" in cmd
        assert "-u https://example.com" in cmd
        assert "-e php,html" in cmd
        assert "-t 30" in cmd

    def test_registration(self):
        task = TaskRegistry.create("dirsearch")
        assert task.name == "dirsearch"


# ── Arjun Parser ───────────────────────────────────────────────────────


class TestArjunParser:
    def test_parse_output(self, tmp_path):
        data = {
            "https://example.com/api": {
                "method": "GET",
                "params": ["id", "page", "token"],
            }
        }
        outfile = tmp_path / "arjun.json"
        outfile.write_text(json.dumps(data))
        task = TaskRegistry.create("arjun")
        results = task.parse_output("", "", output_file=outfile)
        urls = [r for r in results if isinstance(r, Url)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(urls) == 1
        assert urls[0].url == "https://example.com/api"
        assert urls[0].method == "GET"
        assert len(tags) == 3
        param_names = [t.name for t in tags]
        assert "id" in param_names
        assert "page" in param_names
        assert "token" in param_names
        assert all(t.category == "parameter" for t in tags)

    def test_parse_output_empty(self):
        task = TaskRegistry.create("arjun")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("arjun")
        cmd, out_file = task.build_command("https://example.com/api", method="POST", threads=5)
        assert "arjun" in cmd
        assert "-u https://example.com/api" in cmd
        assert "-m POST" in cmd
        assert "-t 5" in cmd
        # arjun has output_flag=-oJ, so output_file should be set
        assert out_file is not None
        # Clean up the temp file
        if out_file and out_file.exists():
            out_file.unlink()

    def test_registration(self):
        task = TaskRegistry.create("arjun")
        assert task.name == "arjun"


# ── Testssl Parser ─────────────────────────────────────────────────────


class TestTestsslParser:
    def test_parse_output(self, tmp_path):
        data = [
            {
                "id": "cert_notAfter",
                "severity": "OK",
                "finding": "2025-01-01",
                "ip": "93.184.216.34",
                "port": "443",
            },
            {
                "id": "LUCKY13",
                "severity": "LOW",
                "finding": "LUCKY13 potentially vulnerable",
                "ip": "93.184.216.34",
                "port": "443",
            },
        ]
        outfile = tmp_path / "testssl.json"
        outfile.write_text(json.dumps(data))
        task = TaskRegistry.create("testssl")
        results = task.parse_output("", "", output_file=outfile)
        from ofx.tasks.output_types import Certificate
        certs = [r for r in results if isinstance(r, Certificate)]
        tags = [r for r in results if isinstance(r, Tag)]
        # cert_notAfter starts with "cert_" → Certificate
        assert len(certs) == 1
        assert certs[0].subject_cn == "2025-01-01"
        assert certs[0].host == "93.184.216.34:443"
        # LUCKY13 severity LOW → Tag (not vuln, no "vuln" in id, severity not medium/high/critical)
        assert len(tags) == 1
        assert tags[0].name == "LUCKY13"
        assert tags[0].value == "LUCKY13 potentially vulnerable"

    def test_parse_output_with_vuln(self):
        data = [
            {
                "id": "BEAST_vuln",
                "severity": "HIGH",
                "finding": "BEAST vulnerability found",
                "ip": "10.0.0.1",
                "port": "443",
            },
        ]
        task = TaskRegistry.create("testssl")
        results = task.parse_output(json.dumps(data), "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        assert len(vulns) == 1
        assert vulns[0].name == "BEAST_vuln"
        assert vulns[0].severity == Severity.HIGH
        assert vulns[0].provider == "testssl"

    def test_parse_output_empty(self):
        task = TaskRegistry.create("testssl")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("testssl")
        cmd, out_file = task.build_command("example.com:443", protocols=True, vulnerabilities=True)
        assert "testssl.sh" in cmd
        assert "-p" in cmd
        assert "-U" in cmd
        assert "example.com:443" in cmd
        # testssl has output_flag=--jsonfile
        assert out_file is not None
        if out_file and out_file.exists():
            out_file.unlink()

    def test_registration(self):
        task = TaskRegistry.create("testssl")
        assert task.name == "testssl"


# ── H8mail Parser ─────────────────────────────────────────────────────


class TestH8mailParser:
    def test_parse_output(self, tmp_path):
        data = {
            "targets": [
                {
                    "target": "user@example.com",
                    "data": [
                        {"breach": "LinkedIn 2012", "password": "pass123"},
                    ],
                }
            ]
        }
        outfile = tmp_path / "h8mail.json"
        outfile.write_text(json.dumps(data))
        task = TaskRegistry.create("h8mail")
        results = task.parse_output("", "", output_file=outfile)
        from ofx.tasks.output_types import UserAccount
        accounts = [r for r in results if isinstance(r, UserAccount)]
        assert len(accounts) == 1
        assert accounts[0].username == "user@example.com"
        assert accounts[0].password == "pass123"
        assert accounts[0].source == "LinkedIn 2012"
        assert accounts[0].extra_data["breach"] == "LinkedIn 2012"

    def test_parse_output_empty(self):
        task = TaskRegistry.create("h8mail")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("h8mail")
        cmd, out_file = task.build_command("user@example.com", chase_limit=10)
        assert "h8mail" in cmd
        assert "-t user@example.com" in cmd
        assert "--chase-limit 10" in cmd
        # h8mail has output_flag=--json
        assert out_file is not None
        if out_file and out_file.exists():
            out_file.unlink()

    def test_registration(self):
        task = TaskRegistry.create("h8mail")
        assert task.name == "h8mail"


# ── Whois Parser ───────────────────────────────────────────────────────


class TestWhoisParser:
    def test_parse_output(self):
        stdout = (
            "Domain Name: EXAMPLE.COM\n"
            "Registrar: Example Registrar, Inc.\n"
            "Creation Date: 1995-08-14T04:00:00Z\n"
            "Registry Expiry Date: 2024-08-13T04:00:00Z\n"
            "Name Server: NS1.EXAMPLE.COM\n"
            "Name Server: NS2.EXAMPLE.COM\n"
        )
        task = TaskRegistry.create("whois")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import Domain
        domains = [r for r in results if isinstance(r, Domain)]
        assert len(domains) == 1
        assert domains[0].domain == "example.com"
        assert domains[0].registrar == "Example Registrar, Inc."
        assert domains[0].creation_date == "1995-08-14T04:00:00Z"
        assert domains[0].expiration_date == "2024-08-13T04:00:00Z"
        assert domains[0].alive is True
        ns = domains[0].extra_data.get("name_servers", [])
        assert "ns1.example.com" in ns
        assert "ns2.example.com" in ns

    def test_parse_output_empty(self):
        task = TaskRegistry.create("whois")
        assert task.parse_output("", "") == []

    def test_command_building(self):
        task = TaskRegistry.create("whois")
        cmd, _ = task.build_command("example.com")
        assert "whois" in cmd
        assert "example.com" in cmd

    def test_registration(self):
        task = TaskRegistry.create("whois")
        assert task.name == "whois"
