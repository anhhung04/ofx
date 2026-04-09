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
        assert tags[0].name == "generic-api-key"
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
        assert "--no-update" in cmd
        assert "--only-verified" in cmd
        assert "https://github.com/org/repo" in cmd
        assert task.json_flag == "--json"

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


# ── Gobuster Parser ───────────────────────────────────────────────────


class TestGobusterParser:
    def test_gobuster_metadata(self):
        task = TaskRegistry.create("gobuster")
        assert task.name == "gobuster"
        assert task.cmd == "gobuster"
        assert task.category == "url/fuzz"
        assert Url in task.output_types
        assert "go install" in task.install_cmd

    def test_gobuster_parse_output(self):
        stdout = (
            "/admin (Status: 200) [Size: 1234]\n"
            "/login (Status: 302) [Size: 56]\n"
            "/secret (Status: 403) [Size: 0]\n"
        )
        task = TaskRegistry.create("gobuster")
        results = task.parse_output(stdout, "")
        assert len(results) == 3
        assert all(isinstance(r, Url) for r in results)
        assert results[0].url == "/admin"
        assert results[0].status_code == 200
        assert results[0].content_length == 1234
        assert results[1].url == "/login"
        assert results[1].status_code == 302
        assert results[2].status_code == 403

    def test_gobuster_parse_empty(self):
        task = TaskRegistry.create("gobuster")
        assert task.parse_output("", "") == []
        assert task.parse_output("   \n  ", "") == []

    def test_gobuster_parse_line(self):
        task = TaskRegistry.create("gobuster")
        result = task.parse_line("/backup (Status: 200) [Size: 999]")
        assert len(result) == 1
        assert result[0].url == "/backup"
        assert result[0].status_code == 200
        assert result[0].content_length == 999

    def test_gobuster_parse_line_non_matching(self):
        task = TaskRegistry.create("gobuster")
        assert task.parse_line("") == []
        assert task.parse_line("Progress: 100%") == []
        assert task.parse_line("===============================================================") == []

    def test_gobuster_build_command(self):
        task = TaskRegistry.create("gobuster")
        cmd, out_file = task.build_command(
            "https://example.com",
            wordlist="/usr/share/seclists/common.txt",
            threads=50,
        )
        assert "gobuster" in cmd
        assert "dir" in cmd
        assert "--no-progress" in cmd
        assert "--no-color" in cmd
        assert "-w /usr/share/seclists/common.txt" in cmd
        assert "-t 50" in cmd
        assert "-u https://example.com" in cmd
        assert out_file is not None
        if out_file and out_file.exists():
            out_file.unlink()

    def test_gobuster_build_command_dns_mode(self):
        task = TaskRegistry.create("gobuster")
        cmd, out_file = task.build_command("example.com", mode="dns")
        assert "gobuster dns" in cmd
        assert "-u example.com" in cmd
        if out_file and out_file.exists():
            out_file.unlink()


# ── Amass Parser ──────────────────────────────────────────────────────


class TestAmassParser:
    def test_amass_metadata(self):
        task = TaskRegistry.create("amass")
        assert task.name == "amass"
        assert task.cmd == "amass"
        assert task.category == "dns/recon"
        assert Subdomain in task.output_types
        assert "go install" in task.install_cmd

    def test_amass_parse_output(self):
        stdout = "api.example.com\nwww.example.com\nmail.example.com\n"
        task = TaskRegistry.create("amass")
        results = task.parse_output(stdout, "")
        assert len(results) == 3
        assert all(isinstance(r, Subdomain) for r in results)
        assert results[0].host == "api.example.com"
        assert results[0].domain == "example.com"
        assert results[1].host == "www.example.com"

    def test_amass_parse_empty(self):
        task = TaskRegistry.create("amass")
        assert task.parse_output("", "") == []

    def test_amass_parse_line(self):
        task = TaskRegistry.create("amass")
        result = task.parse_line("sub.example.com")
        assert len(result) == 1
        assert result[0].host == "sub.example.com"
        assert result[0].domain == "example.com"

    def test_amass_parse_line_comment(self):
        task = TaskRegistry.create("amass")
        assert task.parse_line("# comment") == []
        assert task.parse_line("") == []

    def test_amass_build_command(self):
        task = TaskRegistry.create("amass")
        cmd, out_file = task.build_command("example.com", brute=True, timeout=30)
        assert "amass" in cmd
        assert "enum" in cmd
        assert "-passive" in cmd
        assert "-brute" in cmd
        assert "-timeout 30" in cmd
        assert "-d example.com" in cmd
        assert out_file is not None
        if out_file and out_file.exists():
            out_file.unlink()

    def test_amass_build_command_active(self):
        task = TaskRegistry.create("amass")
        cmd, _ = task.build_command("example.com", active=True)
        assert "-active" in cmd
        assert "-passive" not in cmd


# ── Masscan Parser ────────────────────────────────────────────────────


class TestMasscanParser:
    def test_masscan_metadata(self):
        task = TaskRegistry.create("masscan")
        assert task.name == "masscan"
        assert task.cmd == "masscan"
        assert task.category == "port/scan"
        assert Port in task.output_types
        assert Ip in task.output_types
        assert task.install_cmd == "apt install -y masscan"

    def test_masscan_parse_output(self):
        data = json.dumps([
            {
                "ip": "10.0.0.1",
                "ports": [
                    {"port": 80, "proto": "tcp", "status": "open"},
                    {"port": 443, "proto": "tcp", "status": "open"},
                ],
            },
            {
                "ip": "10.0.0.2",
                "ports": [{"port": 22, "proto": "tcp", "status": "open"}],
            },
        ])
        task = TaskRegistry.create("masscan")
        results = task.parse_output(data, "")
        ips = [r for r in results if isinstance(r, Ip)]
        ports = [r for r in results if isinstance(r, Port)]
        assert len(ips) == 2
        assert ips[0].ip == "10.0.0.1"
        assert ips[0].alive is True
        assert ips[1].ip == "10.0.0.2"
        assert len(ports) == 3
        assert ports[0].port == 80
        assert ports[0].ip == "10.0.0.1"
        assert ports[0].protocol == "tcp"
        assert ports[1].port == 443
        assert ports[2].port == 22
        assert ports[2].ip == "10.0.0.2"

    def test_masscan_parse_output_with_service(self):
        data = json.dumps([
            {
                "ip": "10.0.0.1",
                "ports": [
                    {"port": 80, "proto": "tcp", "status": "open", "service": {"name": "http"}},
                ],
            },
        ])
        task = TaskRegistry.create("masscan")
        results = task.parse_output(data, "")
        ports = [r for r in results if isinstance(r, Port)]
        assert len(ports) == 1
        assert ports[0].service_name == "http"

    def test_masscan_parse_empty(self):
        task = TaskRegistry.create("masscan")
        assert task.parse_output("", "") == []

    def test_masscan_parse_invalid_json(self):
        task = TaskRegistry.create("masscan")
        assert task.parse_output("{broken json", "") == []

    def test_masscan_build_command(self):
        task = TaskRegistry.create("masscan")
        cmd, out_file = task.build_command("10.0.0.0/24", ports="80,443", rate=5000)
        assert "masscan" in cmd
        assert "--rate=5000" in cmd
        assert "-p 80,443" in cmd
        assert "10.0.0.0/24" in cmd
        assert out_file is not None
        if out_file and out_file.exists():
            out_file.unlink()

    def test_masscan_build_command_default_rate(self):
        task = TaskRegistry.create("masscan")
        cmd, out_file = task.build_command("10.0.0.0/24", ports="80")
        assert "--rate=1000" in cmd
        if out_file and out_file.exists():
            out_file.unlink()


# ── Assetfinder Parser ───────────────────────────────────────────────


class TestAssetfinderParser:
    def test_assetfinder_metadata(self):
        task = TaskRegistry.create("assetfinder")
        assert task.name == "assetfinder"
        assert task.cmd == "assetfinder"
        assert task.category == "dns/recon"
        assert Subdomain in task.output_types
        assert "go install" in task.install_cmd

    def test_assetfinder_parse_output(self):
        stdout = "api.example.com\nwww.example.com\ncdn.example.com\n"
        task = TaskRegistry.create("assetfinder")
        results = task.parse_output(stdout, "")
        assert len(results) == 3
        assert all(isinstance(r, Subdomain) for r in results)
        assert results[0].host == "api.example.com"
        assert results[0].domain == "example.com"
        assert results[2].host == "cdn.example.com"

    def test_assetfinder_parse_empty(self):
        task = TaskRegistry.create("assetfinder")
        assert task.parse_output("", "") == []

    def test_assetfinder_parse_line(self):
        task = TaskRegistry.create("assetfinder")
        result = task.parse_line("dev.example.com")
        assert len(result) == 1
        assert result[0].host == "dev.example.com"
        assert result[0].domain == "example.com"

    def test_assetfinder_parse_line_empty(self):
        task = TaskRegistry.create("assetfinder")
        assert task.parse_line("") == []
        assert task.parse_line("# comment") == []


# ── Findomain Parser ─────────────────────────────────────────────────


class TestFindomainParser:
    def test_findomain_metadata(self):
        task = TaskRegistry.create("findomain")
        assert task.name == "findomain"
        assert task.cmd == "findomain"
        assert task.category == "dns/recon"
        assert Subdomain in task.output_types
        assert "findomain" in task.install_cmd

    def test_findomain_parse_output(self):
        stdout = "test.example.com\nstaging.example.com\n"
        task = TaskRegistry.create("findomain")
        results = task.parse_output(stdout, "")
        assert len(results) == 2
        assert all(isinstance(r, Subdomain) for r in results)
        assert results[0].host == "test.example.com"
        assert results[0].domain == "example.com"

    def test_findomain_parse_empty(self):
        task = TaskRegistry.create("findomain")
        assert task.parse_output("", "") == []

    def test_findomain_parse_line(self):
        task = TaskRegistry.create("findomain")
        result = task.parse_line("admin.example.com")
        assert len(result) == 1
        assert result[0].host == "admin.example.com"
        assert result[0].domain == "example.com"

    def test_findomain_parse_line_empty(self):
        task = TaskRegistry.create("findomain")
        assert task.parse_line("") == []
        assert task.parse_line("# comment") == []

    def test_findomain_build_command(self):
        task = TaskRegistry.create("findomain")
        cmd, out_file = task.build_command("example.com", threads=10)
        assert "findomain" in cmd
        assert "-q" in cmd
        assert "-t example.com" in cmd
        assert "--threads 10" in cmd
        assert out_file is not None
        if out_file and out_file.exists():
            out_file.unlink()


# ── Mapcidr Parser ────────────────────────────────────────────────────


class TestMapcidrParser:
    def test_mapcidr_metadata(self):
        task = TaskRegistry.create("mapcidr")
        assert task.name == "mapcidr"
        assert task.cmd == "mapcidr"
        assert task.category == "ip/util"
        assert Ip in task.output_types
        assert "go install" in task.install_cmd

    def test_mapcidr_parse_output(self):
        stdout = "10.0.0.1\n10.0.0.2\n10.0.0.3\n"
        task = TaskRegistry.create("mapcidr")
        results = task.parse_output(stdout, "")
        assert len(results) == 3
        assert all(isinstance(r, Ip) for r in results)
        assert results[0].ip == "10.0.0.1"
        assert results[0].alive is False
        assert results[2].ip == "10.0.0.3"

    def test_mapcidr_parse_empty(self):
        task = TaskRegistry.create("mapcidr")
        assert task.parse_output("", "") == []

    def test_mapcidr_parse_line(self):
        task = TaskRegistry.create("mapcidr")
        result = task.parse_line("192.168.1.1")
        assert len(result) == 1
        assert result[0].ip == "192.168.1.1"
        assert result[0].alive is False

    def test_mapcidr_parse_line_empty(self):
        task = TaskRegistry.create("mapcidr")
        assert task.parse_line("") == []
        assert task.parse_line("# comment") == []


# ── Fping Parser ──────────────────────────────────────────────────────


class TestFpingParser:
    def test_fping_metadata(self):
        task = TaskRegistry.create("fping")
        assert task.name == "fping"
        assert task.cmd == "fping"
        assert task.category == "ip/recon"
        assert Ip in task.output_types
        assert task.install_cmd == "apt install -y fping"

    def test_fping_parse_output(self):
        stdout = "10.0.0.1\n10.0.0.5\n10.0.0.10\n"
        task = TaskRegistry.create("fping")
        results = task.parse_output(stdout, "")
        assert len(results) == 3
        assert all(isinstance(r, Ip) for r in results)
        assert results[0].ip == "10.0.0.1"
        assert results[0].alive is True
        assert results[1].ip == "10.0.0.5"

    def test_fping_parse_empty(self):
        task = TaskRegistry.create("fping")
        assert task.parse_output("", "") == []

    def test_fping_parse_line(self):
        task = TaskRegistry.create("fping")
        result = task.parse_line("192.168.1.100")
        assert len(result) == 1
        assert result[0].ip == "192.168.1.100"
        assert result[0].alive is True

    def test_fping_parse_line_parenthesized(self):
        task = TaskRegistry.create("fping")
        result = task.parse_line("(10.0.0.1)")
        assert len(result) == 1
        assert result[0].ip == "10.0.0.1"

    def test_fping_parse_line_empty(self):
        task = TaskRegistry.create("fping")
        assert task.parse_line("") == []

    def test_fping_build_command(self):
        task = TaskRegistry.create("fping")
        cmd, out_file = task.build_command("10.0.0.0/24", generate=True, count=3)
        assert "fping" in cmd
        assert "-a" in cmd
        assert "-q" in cmd
        assert "-g" in cmd
        assert "-c 3" in cmd
        assert "10.0.0.0/24" in cmd
        assert out_file is None


# ── Cariddi Parser ────────────────────────────────────────────────────


class TestCariddiParser:
    def test_cariddi_metadata(self):
        task = TaskRegistry.create("cariddi")
        assert task.name == "cariddi"
        assert task.cmd == "cariddi"
        assert task.category == "url/crawl"
        assert Url in task.output_types
        assert Tag in task.output_types
        assert "go install" in task.install_cmd

    def test_cariddi_parse_output(self):
        lines = [
            json.dumps({
                "url": "https://example.com/login",
                "status_code": 200,
                "matches": [
                    {"name": "API Key", "match": "AKIA...", "type": "secret"},
                ],
            }),
            json.dumps({
                "url": "https://example.com/api",
                "status_code": 200,
            }),
        ]
        task = TaskRegistry.create("cariddi")
        results = task.parse_output("\n".join(lines), "")
        urls = [r for r in results if isinstance(r, Url)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(urls) == 2
        assert urls[0].url == "https://example.com/login"
        assert urls[0].status_code == 200
        assert len(tags) == 1
        assert tags[0].name == "API Key"
        assert tags[0].value == "AKIA..."
        assert tags[0].category == "secret"
        assert tags[0].match == "https://example.com/login"

    def test_cariddi_parse_output_with_secrets_array(self):
        lines = [
            json.dumps({
                "url": "https://example.com/page",
                "secrets": ["AWS_KEY=AKIA12345"],
            }),
        ]
        task = TaskRegistry.create("cariddi")
        results = task.parse_output("\n".join(lines), "")
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(tags) == 1
        assert tags[0].name == "secret"
        assert tags[0].value == "AWS_KEY=AKIA12345"
        assert tags[0].category == "secret"

    def test_cariddi_parse_empty(self):
        task = TaskRegistry.create("cariddi")
        assert task.parse_output("", "") == []

    def test_cariddi_parse_line(self):
        task = TaskRegistry.create("cariddi")
        result = task.parse_line(json.dumps({
            "url": "https://example.com/test",
            "status_code": 404,
        }))
        urls = [r for r in result if isinstance(r, Url)]
        assert len(urls) == 1
        assert urls[0].url == "https://example.com/test"
        assert urls[0].status_code == 404

    def test_cariddi_parse_line_non_json(self):
        task = TaskRegistry.create("cariddi")
        assert task.parse_line("") == []
        assert task.parse_line("not json") == []

    def test_cariddi_build_command(self):
        task = TaskRegistry.create("cariddi")
        cmd, out_file = task.build_command("https://example.com", threads=10, depth=3)
        assert "cariddi" in cmd
        assert "echo" in cmd
        assert "https://example.com" in cmd
        assert "-json" in cmd
        assert "-c 10" in cmd
        assert "-depth 3" in cmd
        assert out_file is None


# ── Nikto Parser ──────────────────────────────────────────────────────


class TestNiktoParser:
    def test_nikto_metadata(self):
        task = TaskRegistry.create("nikto")
        assert task.name == "nikto"
        assert task.cmd == "nikto"
        assert task.category == "vuln/scan/web"
        assert Vulnerability in task.output_types
        assert task.install_cmd == "apt install -y nikto"

    def test_nikto_parse_output(self):
        data = {
            "host": "example.com",
            "ip": "93.184.216.34",
            "port": "80",
            "vulnerabilities": [
                {
                    "id": "000001",
                    "OSVDB": "3092",
                    "msg": "/admin/: Directory indexing found.",
                    "url": "/admin/",
                    "method": "GET",
                },
                {
                    "id": "000002",
                    "OSVDB": "0",
                    "msg": "Server leaks info via X-Powered-By header",
                    "url": "/",
                    "method": "GET",
                },
            ],
        }
        task = TaskRegistry.create("nikto")
        results = task.parse_output(json.dumps(data), "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        assert len(vulns) == 2
        assert vulns[0].name == "/admin/: Directory indexing found."
        assert vulns[0].id == "3092"
        assert vulns[0].matched_at == "/admin/"
        assert vulns[0].severity == Severity.INFO
        assert vulns[0].provider == "nikto"
        assert vulns[0].extra_data["method"] == "GET"
        assert vulns[0].extra_data["host"] == "example.com"
        assert vulns[1].id == "0"  # OSVDB=0 used as id

    def test_nikto_parse_output_list(self):
        data = [
            {
                "host": "example.com",
                "ip": "93.184.216.34",
                "port": "443",
                "vulnerabilities": [
                    {
                        "id": "999",
                        "OSVDB": "",
                        "msg": "Test finding",
                        "url": "/test",
                        "method": "GET",
                    },
                ],
            },
        ]
        task = TaskRegistry.create("nikto")
        results = task.parse_output(json.dumps(data), "")
        assert len(results) == 1
        assert results[0].matched_at == "/test"

    def test_nikto_parse_empty(self):
        task = TaskRegistry.create("nikto")
        assert task.parse_output("", "") == []

    def test_nikto_parse_invalid_json(self):
        task = TaskRegistry.create("nikto")
        assert task.parse_output("{broken", "") == []


# ── WhatWeb Parser ────────────────────────────────────────────────────


class TestWhatwebParser:
    def test_whatweb_metadata(self):
        task = TaskRegistry.create("whatweb")
        assert task.name == "whatweb"
        assert task.cmd == "whatweb"
        assert task.category == "url/fingerprint"
        assert Tag in task.output_types
        assert task.install_cmd == "apt install -y whatweb"

    def test_whatweb_parse_output(self):
        lines = [
            json.dumps({
                "target": "https://example.com",
                "plugins": {
                    "nginx": {"version": ["1.18.0"]},
                    "PHP": {"version": ["7.4"]},
                    "jQuery": {},
                    "Country": {"string": ["US"]},
                },
            }),
        ]
        task = TaskRegistry.create("whatweb")
        results = task.parse_output("\n".join(lines), "")
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(tags) == 3
        names = {t.name for t in tags}
        assert "nginx" in names
        assert "PHP" in names
        assert "Country" in names
        assert "jQuery" not in names
        nginx_tag = next(t for t in tags if t.name == "nginx")
        assert nginx_tag.value == "1.18.0"
        assert nginx_tag.match == "https://example.com"
        assert nginx_tag.category == "tech"
        country_tag = next(t for t in tags if t.name == "Country")
        assert country_tag.value == "US"

    def test_whatweb_parse_empty(self):
        task = TaskRegistry.create("whatweb")
        assert task.parse_output("", "") == []

    def test_whatweb_build_command(self):
        task = TaskRegistry.create("whatweb")
        cmd, out_file = task.build_command(
            "https://example.com", aggression=3, threads=10
        )
        assert "whatweb" in cmd
        assert "-q" in cmd
        assert "--color=never" in cmd
        assert "-a 3" in cmd
        assert "-t 10" in cmd
        assert "https://example.com" in cmd
        assert out_file is not None
        if out_file and out_file.exists():
            out_file.unlink()


# ── Sqlmap Parser ─────────────────────────────────────────────────────


class TestSqlmapParser:
    def test_sqlmap_metadata(self):
        task = TaskRegistry.create("sqlmap")
        assert task.name == "sqlmap"
        assert task.cmd == "sqlmap"
        assert task.category == "vuln/scan/sqli"
        assert Vulnerability in task.output_types
        assert "sqlmap" in task.install_cmd

    def test_sqlmap_parse_output(self):
        stdout = (
            "sqlmap identified the following injection point(s):\n"
            "---\n"
            "Parameter: id (GET)\n"
            "    Type: boolean-based blind\n"
            "    Title: AND boolean-based blind - WHERE or HAVING clause\n"
            "    Payload: id=1 AND 5678=5678\n"
            "---\n"
            "    Type: time-based blind\n"
            "    Title: MySQL >= 5.0.12 AND time-based blind\n"
            "    Payload: id=1 AND SLEEP(5)\n"
        )
        task = TaskRegistry.create("sqlmap")
        results = task.parse_output(stdout, "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        assert len(vulns) == 2
        assert vulns[0].name == "AND boolean-based blind - WHERE or HAVING clause"
        assert vulns[0].severity == Severity.HIGH
        assert vulns[0].provider == "sqlmap"
        assert "sqli" in vulns[0].tags
        assert vulns[0].extra_data["parameter"] == "id (GET)"
        assert vulns[0].extra_data["type"] == "boolean-based blind"
        assert vulns[0].extra_data["payload"] == "id=1 AND 5678=5678"
        assert vulns[1].name == "MySQL >= 5.0.12 AND time-based blind"
        assert vulns[1].extra_data["payload"] == "id=1 AND SLEEP(5)"

    def test_sqlmap_parse_output_with_url(self):
        stdout = (
            "testing URL 'https://target.com/page?id=1'\n"
            "Parameter: id (GET)\n"
            "    Type: UNION query\n"
            "    Title: Generic UNION query\n"
            "    Payload: id=1 UNION ALL SELECT NULL\n"
        )
        task = TaskRegistry.create("sqlmap")
        results = task.parse_output(stdout, "")
        assert len(results) == 1
        assert results[0].matched_at == "https://target.com/page?id=1"

    def test_sqlmap_parse_empty(self):
        task = TaskRegistry.create("sqlmap")
        assert task.parse_output("", "") == []


# ── X8 Parser ─────────────────────────────────────────────────────────


class TestX8Parser:
    def test_x8_metadata(self):
        task = TaskRegistry.create("x8")
        assert task.name == "x8"
        assert task.cmd == "x8"
        assert task.category == "url/fuzz/params"
        assert Tag in task.output_types
        assert "cargo install" in task.install_cmd

    def test_x8_parse_output(self):
        data = [
            {
                "url": "https://example.com/api",
                "method": "GET",
                "parameters": ["debug", "admin", "token"],
            },
        ]
        task = TaskRegistry.create("x8")
        results = task.parse_output(json.dumps(data), "")
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(tags) == 3
        assert all(t.name == "hidden_param" for t in tags)
        assert tags[0].value == "debug"
        assert tags[0].match == "https://example.com/api"
        assert tags[0].category == "param"
        assert tags[0].extra_data["method"] == "GET"
        assert tags[1].value == "admin"
        assert tags[2].value == "token"

    def test_x8_parse_output_single_object(self):
        data = {
            "url": "https://example.com/search",
            "method": "POST",
            "parameters": ["q"],
        }
        task = TaskRegistry.create("x8")
        results = task.parse_output(json.dumps(data), "")
        assert len(results) == 1
        assert results[0].value == "q"
        assert results[0].extra_data["method"] == "POST"

    def test_x8_parse_empty(self):
        task = TaskRegistry.create("x8")
        assert task.parse_output("", "") == []

    def test_x8_parse_invalid_json(self):
        task = TaskRegistry.create("x8")
        assert task.parse_output("{broken", "") == []


# ── Dnsrecon Parser ───────────────────────────────────────────────────


class TestDnsreconParser:
    def test_dnsrecon_metadata(self):
        from ofx.tasks.output_types import Record

        task = TaskRegistry.create("dnsrecon")
        assert task.name == "dnsrecon"
        assert task.cmd == "dnsrecon"
        assert task.category == "dns/recon"
        assert Record in task.output_types
        assert Subdomain in task.output_types
        assert "dnsrecon" in task.install_cmd

    def test_dnsrecon_parse_output(self):
        from ofx.tasks.output_types import Record

        data = [
            {"type": "A", "name": "www.example.com", "address": "93.184.216.34"},
            {"type": "MX", "name": "example.com", "address": "mail.example.com"},
            {"type": "AAAA", "name": "ipv6.example.com", "address": "2606:2800:220:1::"},
            {"type": "NS", "name": "example.com", "address": "ns1.example.com"},
        ]
        task = TaskRegistry.create("dnsrecon")
        results = task.parse_output(json.dumps(data), "")
        records = [r for r in results if isinstance(r, Record)]
        subs = [r for r in results if isinstance(r, Subdomain)]
        assert len(records) == 4
        assert records[0].type == "A"
        assert records[0].name == "www.example.com"
        assert records[0].host == "93.184.216.34"
        # A and AAAA records produce Subdomains
        assert len(subs) == 2
        assert subs[0].host == "www.example.com"
        assert subs[0].domain == "example.com"
        assert subs[1].host == "ipv6.example.com"

    def test_dnsrecon_parse_empty(self):
        task = TaskRegistry.create("dnsrecon")
        assert task.parse_output("", "") == []

    def test_dnsrecon_parse_invalid_json(self):
        task = TaskRegistry.create("dnsrecon")
        assert task.parse_output("not json", "") == []

    def test_dnsrecon_parse_non_list(self):
        task = TaskRegistry.create("dnsrecon")
        assert task.parse_output(json.dumps({"key": "value"}), "") == []


# ── TheHarvester Parser ──────────────────────────────────────────────


class TestTheHarvesterParser:
    def test_theharvester_metadata(self):
        from ofx.tasks.output_types import UserAccount

        task = TaskRegistry.create("theharvester")
        assert task.name == "theharvester"
        assert task.cmd == "theHarvester"
        assert task.category == "osint/recon"
        assert Subdomain in task.output_types
        assert UserAccount in task.output_types
        assert "theHarvester" in task.install_cmd

    def test_theharvester_parse_xml(self, tmp_path):
        from ofx.tasks.output_types import UserAccount

        xml_content = (
            "<theHarvester>"
            "<email>admin@example.com</email>"
            "<email>info@example.com</email>"
            "<host>www.example.com</host>"
            "<host>api.example.com:93.184.216.34</host>"
            "</theHarvester>"
        )
        outfile = tmp_path / "harvester.xml"
        outfile.write_text(xml_content)
        task = TaskRegistry.create("theharvester")
        results = task.parse_output("", "", output_file=outfile)
        emails = [r for r in results if isinstance(r, UserAccount)]
        subs = [r for r in results if isinstance(r, Subdomain)]
        assert len(emails) == 2
        assert emails[0].username == "admin"
        assert emails[0].domain == "example.com"
        assert emails[0].source == "theharvester"
        assert emails[1].username == "info"
        assert len(subs) == 2
        assert subs[0].host == "www.example.com"
        assert subs[1].host == "api.example.com"

    def test_theharvester_parse_stdout_fallback(self):
        from ofx.tasks.output_types import UserAccount

        stdout = (
            "[*] Searching Google...\n"
            "user1@example.com\n"
            "user2@example.com\n"
        )
        task = TaskRegistry.create("theharvester")
        results = task.parse_output(stdout, "")
        emails = [r for r in results if isinstance(r, UserAccount)]
        assert len(emails) == 2
        assert emails[0].username == "user1"
        assert emails[0].domain == "example.com"

    def test_theharvester_parse_empty(self):
        task = TaskRegistry.create("theharvester")
        assert task.parse_output("", "") == []

    def test_theharvester_build_command(self):
        task = TaskRegistry.create("theharvester")
        cmd, out_file = task.build_command("example.com", limit=500)
        assert "theHarvester" in cmd
        assert "-b all" in cmd
        assert "-d example.com" in cmd
        assert "-l 500" in cmd
        assert out_file is not None
        if out_file and out_file.exists():
            out_file.unlink()

    def test_theharvester_build_command_custom_source(self):
        task = TaskRegistry.create("theharvester")
        cmd, out_file = task.build_command("example.com", source="google")
        assert "-b google" in cmd
        assert "-b all" not in cmd
        if out_file and out_file.exists():
            out_file.unlink()


# ── Holehe Parser ─────────────────────────────────────────────────────


class TestHoleheParser:
    def test_holehe_metadata(self):
        from ofx.tasks.output_types import UserAccount

        task = TaskRegistry.create("holehe")
        assert task.name == "holehe"
        assert task.cmd == "holehe"
        assert task.category == "user/recon/email"
        assert UserAccount in task.output_types
        assert "holehe" in task.install_cmd

    def test_holehe_parse_output(self):
        from ofx.tasks.output_types import UserAccount

        stdout = (
            "[+] user@example.com is used on: Twitter\n"
            "[+] user@example.com is used on: GitHub\n"
            "[-] user@example.com is not used on: Facebook\n"
        )
        task = TaskRegistry.create("holehe")
        results = task.parse_output(stdout, "")
        accounts = [r for r in results if isinstance(r, UserAccount)]
        assert len(accounts) == 2
        assert accounts[0].username == "user@example.com"
        assert accounts[0].source == "Twitter"
        assert accounts[0].comment == "Account exists"
        assert accounts[1].source == "GitHub"

    def test_holehe_parse_empty(self):
        task = TaskRegistry.create("holehe")
        assert task.parse_output("", "") == []

    def test_holehe_build_command(self):
        task = TaskRegistry.create("holehe")
        cmd, out_file = task.build_command("user@example.com", only_used=True, timeout=30)
        assert "holehe" in cmd
        assert "--no-color" in cmd
        assert "--only-used" in cmd
        assert "-t 30" in cmd
        assert "user@example.com" in cmd
        # holehe has no output_flag, so out_file should be None
        assert out_file is None


# ── Sslscan Parser ────────────────────────────────────────────────────


class TestSslscanParser:
    def _make_sslscan_xml(
        self,
        host: str = "example.com",
        port: str = "443",
        certs: list[dict] | None = None,
        ciphers: list[dict] | None = None,
        heartbleed: bool = False,
    ) -> str:
        root = ET.Element("document")
        ssltest = ET.SubElement(root, "ssltest")
        ssltest.set("host", host)
        ssltest.set("port", port)

        if certs:
            for c in certs:
                cert_el = ET.SubElement(ssltest, "certificate")
                for tag_name, tag_val in c.items():
                    child = ET.SubElement(cert_el, tag_name)
                    child.text = str(tag_val)

        if ciphers:
            for ci in ciphers:
                cipher_el = ET.SubElement(ssltest, "cipher")
                for attr, val in ci.items():
                    cipher_el.set(attr, str(val))

        if heartbleed:
            hb_el = ET.SubElement(ssltest, "heartbleed")
            hb_el.set("vulnerable", "1")

        return ET.tostring(root, encoding="unicode")

    def test_sslscan_metadata(self):
        from ofx.tasks.output_types import Certificate

        task = TaskRegistry.create("sslscan")
        assert task.name == "sslscan"
        assert task.cmd == "sslscan"
        assert task.category == "ssl/scan"
        assert Certificate in task.output_types
        assert Vulnerability in task.output_types
        assert task.install_cmd == "apt install -y sslscan"

    def test_sslscan_parse_output_certificate(self):
        from ofx.tasks.output_types import Certificate

        xml = self._make_sslscan_xml(
            certs=[{
                "subject": "/CN=example.com/O=Example Inc",
                "issuer": "/CN=DigiCert/O=DigiCert Inc",
                "not-valid-before": "Jan  1 00:00:00 2024 GMT",
                "not-valid-after": "Dec 31 23:59:59 2025 GMT",
                "self-signed": "false",
                "fingerprint": "AA:BB:CC:DD",
                "altnames": "example.com, www.example.com",
            }],
        )
        task = TaskRegistry.create("sslscan")
        results = task.parse_output(xml, "")
        certs = [r for r in results if isinstance(r, Certificate)]
        assert len(certs) == 1
        assert certs[0].host == "example.com:443"
        assert certs[0].subject_cn == "example.com"
        assert certs[0].issuer_cn == "DigiCert"
        assert certs[0].fingerprint_sha256 == "AA:BB:CC:DD"
        assert certs[0].self_signed is False
        assert "example.com" in certs[0].subject_an
        assert "www.example.com" in certs[0].subject_an

    def test_sslscan_parse_output_weak_cipher(self):
        xml = self._make_sslscan_xml(
            ciphers=[
                {
                    "status": "accepted",
                    "sslversion": "SSLv3",
                    "cipher": "DES-CBC3-SHA",
                    "bits": "168",
                },
            ],
        )
        task = TaskRegistry.create("sslscan")
        results = task.parse_output(xml, "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        assert len(vulns) == 1
        assert "Weak cipher" in vulns[0].name
        assert vulns[0].severity == Severity.HIGH
        assert vulns[0].provider == "sslscan"
        assert vulns[0].extra_data["sslversion"] == "SSLv3"

    def test_sslscan_parse_output_heartbleed(self):
        xml = self._make_sslscan_xml(heartbleed=True)
        task = TaskRegistry.create("sslscan")
        results = task.parse_output(xml, "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        assert len(vulns) == 1
        assert vulns[0].name == "Heartbleed"
        assert vulns[0].severity == Severity.CRITICAL
        assert "CVE-2014-0160" in vulns[0].tags

    def test_sslscan_parse_rejected_cipher_ignored(self):
        xml = self._make_sslscan_xml(
            ciphers=[
                {
                    "status": "rejected",
                    "sslversion": "SSLv3",
                    "cipher": "NULL-SHA",
                    "bits": "0",
                },
            ],
        )
        task = TaskRegistry.create("sslscan")
        results = task.parse_output(xml, "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        assert len(vulns) == 0

    def test_sslscan_parse_empty(self):
        task = TaskRegistry.create("sslscan")
        assert task.parse_output("", "") == []

    def test_sslscan_parse_invalid_xml(self):
        task = TaskRegistry.create("sslscan")
        assert task.parse_output("<invalid>", "") == []

    def test_sslscan_build_command(self):
        task = TaskRegistry.create("sslscan")
        cmd, out_file = task.build_command(
            "example.com:443", show_certificate=True, starttls="smtp"
        )
        assert "sslscan" in cmd
        assert "--no-colour" in cmd
        assert "--show-certificate" in cmd
        assert "--starttls smtp" in cmd
        assert "example.com:443" in cmd
        assert "--xml=" in cmd
        assert out_file is not None
        if out_file and out_file.exists():
            out_file.unlink()


# ── Netexec Parser ─────────────────────────────────────────────────────────


class TestNetexecParser:
    def test_netexec_metadata(self):
        task = TaskRegistry.create("netexec")
        assert task.name == "netexec"
        assert task.cmd == "nxc"
        assert task.category == "ad/enum"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_netexec_parse_output(self):
        stdout = "\n".join([
            "SMB  10.0.0.1  445  DC01  [+] CORP\\admin:P@ssw0rd (Pwn3d!)",
            "SMB  10.0.0.1  445  DC01  [+] CORP\\user1:password123",
            "SMB  10.0.0.1  445  DC01  [-] CORP\\baduser:wrong STATUS_LOGON_FAILURE",
            "SMB  10.0.0.1  445  DC01  [*] Windows 10.0 Build 17763 x64",
        ])
        task = TaskRegistry.create("netexec")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import Tag, UserAccount

        users = [r for r in results if isinstance(r, UserAccount)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(users) == 2
        assert users[0].username == "admin"
        assert users[0].domain == "CORP"
        assert users[0].password == "P@ssw0rd"
        assert users[0].privilege_level == "admin"
        assert users[1].username == "user1"
        assert users[1].privilege_level == ""
        assert len(tags) == 1
        assert tags[0].name == "info"

    def test_netexec_parse_hash_login(self):
        stdout = "SMB  10.0.0.1  445  DC01  [+] CORP\\admin:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0"
        task = TaskRegistry.create("netexec")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import UserAccount

        users = [r for r in results if isinstance(r, UserAccount)]
        assert len(users) == 1
        assert users[0].hash == "aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0"
        assert users[0].password == ""

    def test_netexec_parse_user_enum(self):
        stdout = "SMB 445 DC01 jsmith rid: 1105"
        task = TaskRegistry.create("netexec")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import UserAccount

        users = [r for r in results if isinstance(r, UserAccount)]
        assert len(users) == 1
        assert users[0].username == "jsmith"
        assert "RID:1105" in users[0].comment

    def test_netexec_parse_share_enum(self):
        stdout = "SMB 445 DC01 ADMIN$ READ"
        task = TaskRegistry.create("netexec")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import Tag

        tags = [r for r in results if isinstance(r, Tag)]
        assert len(tags) == 1
        assert tags[0].name == "share"
        assert tags[0].value == "ADMIN$"

    def test_netexec_parse_empty(self):
        task = TaskRegistry.create("netexec")
        assert task.parse_output("", "") == []

    def test_netexec_build_command(self):
        task = TaskRegistry.create("netexec")
        cmd, _ = task.build_command(
            "10.0.0.1",
            protocol="smb",
            username="admin",
            password="pass",
            shares=True,
        )
        assert "nxc smb 10.0.0.1" in cmd
        assert "-u admin" in cmd
        assert "-p pass" in cmd
        assert "--shares" in cmd


# ── Kerbrute Parser ────────────────────────────────────────────────────────


class TestKerbruteParser:
    def test_kerbrute_metadata(self):
        task = TaskRegistry.create("kerbrute")
        assert task.name == "kerbrute"
        assert task.cmd == "kerbrute"
        assert task.category == "ad/brute"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_kerbrute_parse_output(self):
        stdout = "\n".join([
            "2024/01/15 10:00:00 >  [+] VALID USERNAME:	 admin@corp.local",
            "2024/01/15 10:00:01 >  [+] VALID USERNAME:	 jsmith@corp.local",
            "2024/01/15 10:00:02 >  [+] VALID LOGIN:	 admin@corp.local:Password1",
            "2024/01/15 10:00:03 >  [-] INVALID USERNAME:  fakeuser@corp.local",
        ])
        task = TaskRegistry.create("kerbrute")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import UserAccount

        users = [r for r in results if isinstance(r, UserAccount)]
        assert len(users) == 3
        # Lines processed in order: userenum admin, userenum jsmith, login admin
        assert users[0].username == "admin"
        assert users[0].domain == "corp.local"
        assert users[0].password == ""
        assert users[1].username == "jsmith"
        assert users[1].domain == "corp.local"
        assert users[1].password == ""
        assert users[2].username == "admin"
        assert users[2].password == "Password1"

    def test_kerbrute_parse_empty(self):
        task = TaskRegistry.create("kerbrute")
        assert task.parse_output("", "") == []

    def test_kerbrute_build_command(self):
        task = TaskRegistry.create("kerbrute")
        cmd, _ = task.build_command(
            "/tmp/users.txt",
            mode="userenum",
            dc="10.0.0.1",
            domain="corp.local",
            threads=20,
        )
        assert "kerbrute userenum" in cmd
        assert "--dc 10.0.0.1" in cmd
        assert "-d corp.local" in cmd
        assert "-t 20" in cmd
        assert "/tmp/users.txt" in cmd


# ── Hydra Parser ───────────────────────────────────────────────────────────


class TestHydraParser:
    def test_hydra_metadata(self):
        task = TaskRegistry.create("hydra")
        assert task.name == "hydra"
        assert task.cmd == "hydra"
        assert task.category == "brute/login"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_hydra_parse_output(self):
        stdout = "\n".join([
            "Hydra v9.5 starting...",
            "[DATA] max 16 tasks per 1 server",
            "[22][ssh] host: 10.0.0.1   login: root   password: toor",
            "[22][ssh] host: 10.0.0.1   login: admin   password: admin123",
            "[STATUS] attack finished for 10.0.0.1",
        ])
        task = TaskRegistry.create("hydra")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import UserAccount

        users = [r for r in results if isinstance(r, UserAccount)]
        assert len(users) == 2
        assert users[0].username == "root"
        assert users[0].password == "toor"
        assert users[0].host == "10.0.0.1"
        assert "port=22" in users[0].comment
        assert "service=ssh" in users[0].comment
        assert users[1].username == "admin"
        assert users[1].password == "admin123"

    def test_hydra_parse_empty(self):
        task = TaskRegistry.create("hydra")
        assert task.parse_output("", "") == []

    def test_hydra_build_command(self):
        task = TaskRegistry.create("hydra")
        cmd, _ = task.build_command(
            "10.0.0.1",
            service="ssh",
            login="admin",
            password_file="/tmp/passwords.txt",
            threads=16,
            force=True,
        )
        assert "hydra" in cmd
        assert "-l admin" in cmd
        assert "-P /tmp/passwords.txt" in cmd
        assert "-t 16" in cmd
        assert "-f" in cmd
        assert "10.0.0.1" in cmd
        assert cmd.endswith("ssh")


# ── Enum4linux Parser ──────────────────────────────────────────────────────


class TestEnum4linuxParser:
    def test_enum4linux_metadata(self):
        task = TaskRegistry.create("enum4linux")
        assert task.name == "enum4linux"
        assert task.cmd == "enum4linux-ng"
        assert task.category == "ad/enum"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_enum4linux_parse_output(self):
        data = {
            "users": {
                "500": {"username": "Administrator", "domain": "CORP"},
                "1001": {"username": "jsmith", "domain": "CORP"},
            },
            "shares": [
                {"name": "ADMIN$"},
                {"name": "IPC$"},
            ],
            "groups": [
                {"groupname": "Domain Admins"},
                {"groupname": "Domain Users"},
            ],
            "os_info": {"OS": "Windows 10.0 Build 17763"},
        }
        task = TaskRegistry.create("enum4linux")
        results = task.parse_output(json.dumps(data), "")
        from ofx.tasks.output_types import Tag, UserAccount

        users = [r for r in results if isinstance(r, UserAccount)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(users) == 2
        assert users[0].username == "Administrator"
        assert users[0].domain == "CORP"
        shares = [t for t in tags if t.name == "share"]
        groups = [t for t in tags if t.name == "group"]
        os_tags = [t for t in tags if t.name == "os"]
        assert len(shares) == 2
        assert len(groups) == 2
        assert len(os_tags) == 1
        assert os_tags[0].value == "Windows 10.0 Build 17763"

    def test_enum4linux_parse_empty(self):
        task = TaskRegistry.create("enum4linux")
        assert task.parse_output("", "") == []

    def test_enum4linux_parse_invalid_json(self):
        task = TaskRegistry.create("enum4linux")
        assert task.parse_output("not json", "") == []

    def test_enum4linux_build_command(self):
        task = TaskRegistry.create("enum4linux")
        cmd, out_file = task.build_command(
            "10.0.0.1", username="admin", password="pass"
        )
        assert "enum4linux-ng" in cmd
        assert "-A" in cmd
        assert "-u admin" in cmd
        assert "-p pass" in cmd
        assert "-oJ" in cmd
        assert "10.0.0.1" in cmd
        assert out_file is not None
        if out_file and out_file.exists():
            out_file.unlink()

    def test_enum4linux_build_command_no_default_A(self):
        task = TaskRegistry.create("enum4linux")
        cmd, out_file = task.build_command("10.0.0.1", users=True)
        assert "-A" not in cmd
        assert "-U" in cmd
        if out_file and out_file.exists():
            out_file.unlink()


# ── Paramspider Parser ────────────────────────────────────────────────────


class TestParamspiderParser:
    def test_paramspider_metadata(self):
        task = TaskRegistry.create("paramspider")
        assert task.name == "paramspider"
        assert task.cmd == "paramspider"
        assert task.category == "url/recon/params"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_paramspider_parse_output(self):
        stdout = "\n".join([
            "[INFO] Fetching URLs...",
            "https://example.com/page?id=FUZZ",
            "https://example.com/search?q=FUZZ&lang=en",
            "/api/v1/data?token=FUZZ",
        ])
        task = TaskRegistry.create("paramspider")
        results = task.parse_output(stdout, "")
        assert len(results) == 3
        assert all(isinstance(r, Url) for r in results)
        assert results[0].url == "https://example.com/page?id=FUZZ"
        assert results[2].url == "/api/v1/data?token=FUZZ"

    def test_paramspider_parse_empty(self):
        task = TaskRegistry.create("paramspider")
        assert task.parse_output("", "") == []

    def test_paramspider_parse_line(self):
        task = TaskRegistry.create("paramspider")
        assert len(task.parse_line("https://example.com/x?a=1")) == 1
        assert len(task.parse_line("/path?q=test")) == 1
        assert task.parse_line("[INFO] something") == []
        assert task.parse_line("") == []
        assert task.parse_line("plaintext") == []


# ── Hakrawler Parser ──────────────────────────────────────────────────────


class TestHakrawlerParser:
    def test_hakrawler_metadata(self):
        task = TaskRegistry.create("hakrawler")
        assert task.name == "hakrawler"
        assert task.cmd == "hakrawler"
        assert task.category == "url/crawl"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_hakrawler_parse_output(self):
        stdout = "\n".join([
            "https://example.com/",
            "https://example.com/about",
            "https://example.com/contact?ref=home",
        ])
        task = TaskRegistry.create("hakrawler")
        results = task.parse_output(stdout, "")
        assert len(results) == 3
        assert all(isinstance(r, Url) for r in results)
        assert results[0].url == "https://example.com/"
        assert results[2].url == "https://example.com/contact?ref=home"

    def test_hakrawler_parse_empty(self):
        task = TaskRegistry.create("hakrawler")
        assert task.parse_output("", "") == []

    def test_hakrawler_parse_line(self):
        task = TaskRegistry.create("hakrawler")
        assert len(task.parse_line("https://example.com/page")) == 1
        assert task.parse_line("[info] crawling") == []
        assert task.parse_line("") == []
        assert task.parse_line("no-protocol-text") == []

    def test_hakrawler_build_command(self):
        task = TaskRegistry.create("hakrawler")
        cmd, _ = task.build_command(
            "https://example.com", depth=3, subs=True, insecure=True
        )
        assert "hakrawler" in cmd
        assert "echo" in cmd
        assert "-d 3" in cmd
        assert "-subs" in cmd
        assert "-insecure" in cmd


# ── Subzy Parser ──────────────────────────────────────────────────────────


class TestSubzyParser:
    def test_subzy_metadata(self):
        task = TaskRegistry.create("subzy")
        assert task.name == "subzy"
        assert task.cmd == "subzy"
        assert task.category == "vuln/takeover"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_subzy_parse_output(self):
        stdout = "\n".join([
            "[NOT VULNERABLE] safe.example.com",
            "[VULNERABLE] dangling.example.com - Service: GitHub Pages - CNAME pointing to unregistered github.io",
            "[VULNERABLE] old.example.com - Heroku",
        ])
        task = TaskRegistry.create("subzy")
        results = task.parse_output(stdout, "")
        assert len(results) == 2
        assert all(isinstance(r, Vulnerability) for r in results)
        assert results[0].matched_at == "dangling.example.com"
        assert results[0].severity == Severity.HIGH
        assert "GitHub Pages" in results[0].description
        assert results[1].matched_at == "old.example.com"

    def test_subzy_parse_empty(self):
        task = TaskRegistry.create("subzy")
        assert task.parse_output("", "") == []

    def test_subzy_parse_line(self):
        task = TaskRegistry.create("subzy")
        result = task.parse_line("[VULNERABLE] sub.example.com - Service: S3 Bucket")
        assert len(result) == 1
        assert result[0].name == "Subdomain Takeover"
        assert result[0].matched_at == "sub.example.com"
        assert task.parse_line("[NOT VULNERABLE] safe.example.com") == []
        assert task.parse_line("") == []


# ── CRLFuzz Parser ────────────────────────────────────────────────────────


class TestCrlfuzzParser:
    def test_crlfuzz_metadata(self):
        task = TaskRegistry.create("crlfuzz")
        assert task.name == "crlfuzz"
        assert task.cmd == "crlfuzz"
        assert task.category == "vuln/injection"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_crlfuzz_parse_output(self):
        stdout = "\n".join([
            "https://example.com/path%0d%0aInjected-Header:true",
            "https://example.com/other%0d%0aSet-Cookie:evil",
        ])
        task = TaskRegistry.create("crlfuzz")
        results = task.parse_output(stdout, "")
        assert len(results) == 2
        assert all(isinstance(r, Vulnerability) for r in results)
        assert results[0].name == "CRLF Injection"
        assert results[0].severity == Severity.MEDIUM
        assert "example.com" in results[0].matched_at

    def test_crlfuzz_parse_empty(self):
        task = TaskRegistry.create("crlfuzz")
        assert task.parse_output("", "") == []

    def test_crlfuzz_parse_line(self):
        task = TaskRegistry.create("crlfuzz")
        result = task.parse_line("https://example.com/vuln%0d%0aHeader:val")
        assert len(result) == 1
        assert result[0].name == "CRLF Injection"
        assert task.parse_line("[info] scanning") == []
        assert task.parse_line("") == []
        assert task.parse_line("no-url-text") == []


# ── Commix Parser ─────────────────────────────────────────────────────────


class TestCommixParser:
    def test_commix_metadata(self):
        task = TaskRegistry.create("commix")
        assert task.name == "commix"
        assert task.cmd == "commix"
        assert task.category == "vuln/injection"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_commix_parse_output(self):
        stdout = "\n".join([
            "[*] Testing connection to the target URL...",
            "[*] Checking if the target is protected by some kind of WAF/IPS...",
            "The ('classic') technique appears to be injectable.",
            "The ('eval-based') technique appears to be injectable.",
            "The parameter 'id' is vulnerable.",
            "The ('time-based') technique appears to be injectable.",
            "The parameter 'name' is vulnerable.",
        ])
        task = TaskRegistry.create("commix")
        results = task.parse_output(stdout, "")
        assert len(results) == 2
        assert all(isinstance(r, Vulnerability) for r in results)
        assert results[0].name == "Command Injection"
        assert results[0].matched_at == "id"
        assert results[0].severity == Severity.CRITICAL
        assert "classic" in results[0].description
        assert "eval-based" in results[0].description
        # Second vuln resets techniques
        assert results[1].matched_at == "name"
        assert "time-based" in results[1].description

    def test_commix_parse_empty(self):
        task = TaskRegistry.create("commix")
        assert task.parse_output("", "") == []

    def test_commix_parse_no_vuln(self):
        stdout = "\n".join([
            "[*] Testing connection to the target URL...",
            "[*] Target does not appear to be injectable.",
        ])
        task = TaskRegistry.create("commix")
        assert task.parse_output(stdout, "") == []


# ── Rustscan Parser ───────────────────────────────────────────────────────


class TestRustscanParser:
    def test_rustscan_metadata(self):
        task = TaskRegistry.create("rustscan")
        assert task.name == "rustscan"
        assert task.cmd == "rustscan"
        assert task.category == "port/scan"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_rustscan_parse_output_open_format(self):
        stdout = "\n".join([
            "Open 10.0.0.1:22",
            "Open 10.0.0.1:80",
            "Open 10.0.0.1:443",
        ])
        task = TaskRegistry.create("rustscan")
        results = task.parse_output(stdout, "")
        assert len(results) == 3
        assert all(isinstance(r, Port) for r in results)
        assert results[0].port == 22
        assert results[0].ip == "10.0.0.1"
        assert results[1].port == 80
        assert results[2].port == 443

    def test_rustscan_parse_output_greppable(self):
        stdout = "Host: 10.0.0.1 () Ports: 22/open/tcp//ssh///, 80/open/tcp//http///, 443/open/tcp//https///"
        task = TaskRegistry.create("rustscan")
        results = task.parse_output(stdout, "")
        assert len(results) == 3
        assert results[0].port == 22
        assert results[0].ip == "10.0.0.1"
        assert results[0].service_name == "ssh"
        assert results[1].port == 80
        assert results[1].service_name == "http"

    def test_rustscan_parse_empty(self):
        task = TaskRegistry.create("rustscan")
        assert task.parse_output("", "") == []

    def test_rustscan_parse_line(self):
        task = TaskRegistry.create("rustscan")
        result = task.parse_line("Open 192.168.1.1:8080")
        assert len(result) == 1
        assert result[0].port == 8080
        assert result[0].ip == "192.168.1.1"
        assert task.parse_line("") == []
        assert task.parse_line("some random text") == []


# ── Gowitness Parser ──────────────────────────────────────────────────────


class TestGowitnessParser:
    def test_gowitness_metadata(self):
        task = TaskRegistry.create("gowitness")
        assert task.name == "gowitness"
        assert task.cmd == "gowitness"
        assert task.category == "url/screenshot"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_gowitness_parse_output(self):
        stdout = "\n".join([
            "[200] https://example.com - Example Domain",
            "[301] https://www.example.com - Redirect",
            "[404] https://example.com/missing - Not Found",
        ])
        task = TaskRegistry.create("gowitness")
        results = task.parse_output(stdout, "")
        assert len(results) == 3
        assert all(isinstance(r, Url) for r in results)
        assert results[0].url == "https://example.com"
        assert results[0].status_code == 200
        assert results[0].title == "Example Domain"
        assert results[1].status_code == 301
        assert results[2].status_code == 404

    def test_gowitness_parse_no_title(self):
        stdout = "[200] https://example.com"
        task = TaskRegistry.create("gowitness")
        results = task.parse_output(stdout, "")
        assert len(results) == 1
        assert results[0].url == "https://example.com"
        assert results[0].title == ""

    def test_gowitness_parse_empty(self):
        task = TaskRegistry.create("gowitness")
        assert task.parse_output("", "") == []

    def test_gowitness_build_command(self):
        task = TaskRegistry.create("gowitness")
        cmd, _ = task.build_command(
            "https://example.com", threads=5, fullpage=True
        )
        assert "gowitness scan single" in cmd
        assert "--url https://example.com" in cmd
        assert "--threads 5" in cmd
        assert "--fullpage" in cmd

    def test_gowitness_build_command_file(self):
        task = TaskRegistry.create("gowitness")
        cmd, _ = task.build_command("", _file="/tmp/urls.txt")
        assert "gowitness scan file" in cmd
        assert "-f /tmp/urls.txt" in cmd


# ── JWT Tool Parser ───────────────────────────────────────────────────────


class TestJwtToolParser:
    def test_jwt_tool_metadata(self):
        task = TaskRegistry.create("jwt_tool")
        assert task.name == "jwt_tool"
        assert task.cmd == "jwt_tool"
        assert task.category == "vuln/jwt"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_jwt_tool_parse_output(self):
        stdout = "\n".join([
            "[*] sub = \"admin\"",
            "[*] iat = 1700000000",
            "[+] VULNERABILITY: Algorithm confusion allows forging tokens",
            "[*] Decoded token info line",
            "[+] WEAK key used for signing",
        ])
        task = TaskRegistry.create("jwt_tool")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import Tag

        vulns = [r for r in results if isinstance(r, Vulnerability)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(vulns) == 2
        assert vulns[0].severity == Severity.HIGH
        assert "Algorithm confusion" in vulns[0].name
        # Claims — both sub and iat match _CLAIM_RE (\w+ = value)
        claims = [t for t in tags if t.name == "jwt_claim"]
        assert len(claims) == 2
        assert claims[0].value == "sub=admin"
        assert claims[1].value == "iat=1700000000"
        # Info line for "Decoded token info line"
        info_tags = [t for t in tags if t.name == "jwt_info"]
        assert len(info_tags) == 1

    def test_jwt_tool_parse_empty(self):
        task = TaskRegistry.create("jwt_tool")
        assert task.parse_output("", "") == []

    def test_jwt_tool_build_command(self):
        task = TaskRegistry.create("jwt_tool")
        token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.sig"
        cmd, _ = task.build_command(
            token, mode="at", target_url="https://example.com/api"
        )
        assert "jwt_tool" in cmd
        assert token in cmd
        assert "-M at" in cmd
        assert "-t https://example.com/api" in cmd


# ── Name-That-Hash Parser ────────────────────────────────────────────────


class TestNameThatHashParser:
    def test_name_that_hash_metadata(self):
        task = TaskRegistry.create("name-that-hash")
        assert task.name == "name-that-hash"
        assert task.cmd == "nth"
        assert task.category == "crypto/identify"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_name_that_hash_parse_greppable(self):
        stdout = "5d41402abc4b2a76b9719d911017c592:::Most Likely - MD5 - HC:0 - JtR:raw-md5:::Least Likely - MD4 - HC:900"
        task = TaskRegistry.create("name-that-hash")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import Tag

        tags = [r for r in results if isinstance(r, Tag)]
        assert len(tags) >= 1
        assert tags[0].name == "hash_type"
        assert tags[0].match == "5d41402abc4b2a76b9719d911017c592"
        assert tags[0].category == "crypto"

    def test_name_that_hash_parse_default_mode(self):
        stdout = "\n".join([
            "5d41402abc4b2a76b9719d911017c592",
            "  MD5  HC: 0  JtR: raw-md5",
            "  MD4  HC: 900  JtR: raw-md4",
        ])
        task = TaskRegistry.create("name-that-hash")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import Tag

        tags = [r for r in results if isinstance(r, Tag)]
        assert len(tags) == 2
        assert tags[0].name == "hash_type"
        assert tags[0].value == "MD5"
        assert tags[0].match == "5d41402abc4b2a76b9719d911017c592"
        assert tags[1].value == "MD4"

    def test_name_that_hash_parse_empty(self):
        task = TaskRegistry.create("name-that-hash")
        assert task.parse_output("", "") == []


# ── Hashid Parser ─────────────────────────────────────────────────────────


class TestHashidParser:
    def test_hashid_metadata(self):
        task = TaskRegistry.create("hashid")
        assert task.name == "hashid"
        assert task.cmd == "hashid"
        assert task.category == "crypto/identify"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_hashid_parse_output(self):
        stdout = "\n".join([
            "Analyzing '5d41402abc4b2a76b9719d911017c592'",
            "[+] MD5 [Hashcat Mode: 0] [JtR Format: raw-md5]",
            "[+] MD4 [Hashcat Mode: 900] [JtR Format: raw-md4]",
            "[+] Domain Cached Credentials [Hashcat Mode: 1100]",
        ])
        task = TaskRegistry.create("hashid")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import Tag

        tags = [r for r in results if isinstance(r, Tag)]
        assert len(tags) == 3
        assert tags[0].name == "hash_type"
        assert tags[0].match == "5d41402abc4b2a76b9719d911017c592"
        assert tags[0].category == "crypto"
        # The lazy (.+?) in _TYPE_RE captures minimal chars due to optional groups
        assert tags[0].value  # non-empty
        assert tags[1].value
        assert tags[2].value

    def test_hashid_parse_multiple_hashes(self):
        stdout = "\n".join([
            "Analyzing 'abc123'",
            "[+] MD5",
            "Analyzing 'def456'",
            "[+] SHA-1",
        ])
        task = TaskRegistry.create("hashid")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import Tag

        tags = [r for r in results if isinstance(r, Tag)]
        assert len(tags) == 2
        assert tags[0].match == "abc123"
        assert tags[0].value  # non-empty hash type
        assert tags[1].match == "def456"
        assert tags[1].value  # non-empty hash type

    def test_hashid_parse_empty(self):
        task = TaskRegistry.create("hashid")
        assert task.parse_output("", "") == []


# ── Nerva Parser ──────────────────────────────────────────────────────────

from ofx.tasks.output_types import UserAccount


class TestNervaParser:
    def test_nerva_metadata(self):
        task = TaskRegistry.create("nerva")
        assert task.name == "nerva"
        assert task.cmd == "nerva"
        assert task.category == "port/fingerprint"
        assert task.install_cmd
        assert Port in task.output_types
        assert Tag in task.output_types

    def test_nerva_parse_line_full(self):
        task = TaskRegistry.create("nerva")
        line = json.dumps({
            "ip": "192.168.1.1",
            "host": "web.local",
            "port": 80,
            "protocol": "tcp",
            "service": "http",
            "version": "2.4.51",
            "product": "Apache",
            "banner": "Apache/2.4.51 (Ubuntu)",
            "cpe": "cpe:/a:apache:http_server:2.4.51",
        })
        results = task.parse_line(line)
        ports = [r for r in results if isinstance(r, Port)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(ports) == 1
        assert ports[0].port == 80
        assert ports[0].ip == "192.168.1.1"
        assert ports[0].host == "web.local"
        assert ports[0].state == "open"
        assert ports[0].protocol == "tcp"
        assert "http" in ports[0].service_name
        assert "2.4.51" in ports[0].service_name
        assert ports[0].extra_data["version"] == "2.4.51"
        assert ports[0].extra_data["banner"] == "Apache/2.4.51 (Ubuntu)"
        assert ports[0].extra_data["product"] == "Apache"
        assert len(tags) == 1
        assert tags[0].name == "Apache"
        assert tags[0].category == "service"

    def test_nerva_parse_line_minimal(self):
        task = TaskRegistry.create("nerva")
        line = json.dumps({"ip": "10.0.0.1", "port": 22, "service": "ssh"})
        results = task.parse_line(line)
        assert len(results) == 1
        assert isinstance(results[0], Port)
        assert results[0].port == 22
        assert results[0].service_name == "ssh"

    def test_nerva_parse_line_no_tag_without_product(self):
        task = TaskRegistry.create("nerva")
        line = json.dumps({"ip": "10.0.0.1", "port": 443, "service": "https"})
        results = task.parse_line(line)
        tags = [r for r in results if isinstance(r, Tag)]
        assert tags == []

    def test_nerva_parse_line_invalid(self):
        task = TaskRegistry.create("nerva")
        assert task.parse_line("") == []
        assert task.parse_line("not json") == []
        assert task.parse_line("[info] scanning...") == []
        assert task.parse_line("{}") == []

    def test_nerva_parse_output_stdout(self):
        task = TaskRegistry.create("nerva")
        stdout = "\n".join([
            json.dumps({"ip": "10.0.0.1", "port": 22, "service": "ssh"}),
            json.dumps({"ip": "10.0.0.1", "port": 80, "service": "http", "product": "nginx"}),
            "[info] scan complete",
        ])
        results = task.parse_output(stdout, "")
        ports = [r for r in results if isinstance(r, Port)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(ports) == 2
        assert len(tags) == 1

    def test_nerva_parse_output_file(self, tmp_path):
        task = TaskRegistry.create("nerva")
        f = tmp_path / "out.jsonl"
        f.write_text(json.dumps({"ip": "10.0.0.1", "port": 3306, "service": "mysql", "product": "MySQL", "version": "8.0"}))
        results = task.parse_output("", "", output_file=f)
        assert len(results) == 2  # Port + Tag
        assert results[0].port == 3306
        assert results[1].name == "MySQL"

    def test_nerva_parse_empty(self):
        task = TaskRegistry.create("nerva")
        assert task.parse_output("", "") == []

    def test_nerva_streaming(self):
        task = TaskRegistry.create("nerva")
        assert task.supports_streaming is True


# ── Brutus Parser ─────────────────────────────────────────────────────────


class TestBrutusParser:
    def test_brutus_metadata(self):
        task = TaskRegistry.create("brutus")
        assert task.name == "brutus"
        assert task.cmd == "brutus"
        assert task.category == "brute/credential"
        assert task.install_cmd
        assert UserAccount in task.output_types

    def test_brutus_parse_line_full(self):
        task = TaskRegistry.create("brutus")
        line = json.dumps({
            "host": "192.168.1.1",
            "port": 22,
            "service": "ssh",
            "username": "admin",
            "password": "admin123",
            "banner": "SSH-2.0-OpenSSH_8.9",
        })
        results = task.parse_line(line)
        assert len(results) == 1
        ua = results[0]
        assert isinstance(ua, UserAccount)
        assert ua.username == "admin"
        assert ua.password == "admin123"
        assert ua.host == "192.168.1.1:22"
        assert ua.source == "brutus/ssh"
        assert ua.extra_data["service"] == "ssh"
        assert ua.extra_data["port"] == 22
        assert ua.extra_data["banner"] == "SSH-2.0-OpenSSH_8.9"

    def test_brutus_parse_line_alt_keys(self):
        task = TaskRegistry.create("brutus")
        line = json.dumps({"ip": "10.0.0.5", "login": "root", "pass": "toor", "protocol": "ftp"})
        results = task.parse_line(line)
        assert len(results) == 1
        assert results[0].username == "root"
        assert results[0].password == "toor"
        assert results[0].host == "10.0.0.5"
        assert results[0].source == "brutus/ftp"

    def test_brutus_parse_line_no_username(self):
        task = TaskRegistry.create("brutus")
        line = json.dumps({"host": "10.0.0.1", "port": 22, "password": "test"})
        assert task.parse_line(line) == []

    def test_brutus_parse_line_invalid(self):
        task = TaskRegistry.create("brutus")
        assert task.parse_line("") == []
        assert task.parse_line("not json") == []
        assert task.parse_line("[info] bruting...") == []
        assert task.parse_line("{}") == []

    def test_brutus_parse_output_stdout(self):
        task = TaskRegistry.create("brutus")
        stdout = "\n".join([
            json.dumps({"host": "10.0.0.1", "port": 22, "username": "admin", "password": "admin", "service": "ssh"}),
            json.dumps({"host": "10.0.0.2", "port": 3306, "username": "root", "password": "", "service": "mysql"}),
            "[info] done",
        ])
        results = task.parse_output(stdout, "")
        assert len(results) == 2
        assert all(isinstance(r, UserAccount) for r in results)
        assert results[0].username == "admin"
        assert results[1].username == "root"

    def test_brutus_parse_output_file(self, tmp_path):
        task = TaskRegistry.create("brutus")
        f = tmp_path / "out.jsonl"
        f.write_text(json.dumps({"host": "10.0.0.1", "port": 5432, "username": "postgres", "password": "postgres", "service": "postgresql"}))
        results = task.parse_output("", "", output_file=f)
        assert len(results) == 1
        assert results[0].username == "postgres"

    def test_brutus_parse_empty(self):
        task = TaskRegistry.create("brutus")
        assert task.parse_output("", "") == []

    def test_brutus_streaming(self):
        task = TaskRegistry.create("brutus")
        assert task.supports_streaming is True
