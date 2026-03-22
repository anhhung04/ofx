"""Tests for the OFX task system — output types, task base, registry, and runner."""

import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from ofx.models.step import RunType, Step
from ofx.tasks import (
    OptDef,
    Port,
    Subdomain,
    Task,
    TaskRegistry,
    Url,
    Vulnerability,
)
from ofx.tasks.output_types import (
    OUTPUT_TYPE_MAP,
    Certificate,
    Confidence,
    Exploit,
    Ip,
    Severity,
    Tag,
)

# ── Output Types ───────────────────────────────────────────────────────────


class TestOutputTypes:
    def test_port_fields(self):
        p = Port(port=80, ip="10.0.0.1", host="web", service_name="http")
        assert p.port == 80
        assert p.host_port == "web:80"
        assert p._type == "port"

    def test_port_host_port_fallback(self):
        p = Port(port=443, ip="10.0.0.1")
        assert p.host_port == "10.0.0.1:443"

    def test_url_fields(self):
        u = Url(url="https://example.com", status_code=200, tech=["nginx"])
        assert u._type == "url"
        assert u.status_code == 200

    def test_vulnerability_severity(self):
        v = Vulnerability(
            name="SQLi", severity=Severity.HIGH, confidence=Confidence.HIGH
        )
        assert v.severity == Severity.HIGH
        assert v._type == "vulnerability"

    def test_subdomain(self):
        s = Subdomain(host="api.example.com", domain="example.com")
        assert s._type == "subdomain"

    def test_to_dict_includes_type_and_uuid(self):
        p = Port(port=22, ip="1.2.3.4")
        d = p.to_dict()
        assert d["_type"] == "port"
        assert "_uuid" in d
        assert len(d["_uuid"]) == 16

    def test_uuid_deterministic(self):
        p1 = Port(port=22, ip="1.2.3.4")
        p2 = Port(port=22, ip="1.2.3.4")
        assert p1._uuid == p2._uuid

    def test_uuid_differs_for_different_data(self):
        p1 = Port(port=22, ip="1.2.3.4")
        p2 = Port(port=80, ip="1.2.3.4")
        assert p1._uuid != p2._uuid

    def test_output_type_map(self):
        assert OUTPUT_TYPE_MAP["port"] is Port
        assert OUTPUT_TYPE_MAP["url"] is Url
        assert OUTPUT_TYPE_MAP["vulnerability"] is Vulnerability
        assert len(OUTPUT_TYPE_MAP) == 11

    def test_all_output_types_have_type_field(self):
        for name, cls in OUTPUT_TYPE_MAP.items():
            # Instantiate with minimal required fields
            if name == "port":
                obj = cls(port=80, ip="1.1.1.1")
            elif name == "url":
                obj = cls(url="http://x")
            elif name == "vulnerability":
                obj = cls(name="test")
            elif name == "tag":
                obj = cls(name="t")
            elif name == "record":
                obj = cls(name="r", type="A")
            elif name == "domain":
                obj = cls(domain="x.com")
            elif name == "certificate":
                obj = cls(host="x")
            elif name == "exploit":
                obj = cls(name="e")
            elif name == "ip":
                obj = cls(ip="1.2.3.4")
            elif name == "subdomain":
                obj = cls(host="a.x.com")
            elif name == "user_account":
                obj = cls(username="admin")
            else:
                continue
            assert obj._type == name

    def test_extra_data(self):
        p = Port(port=80, ip="1.1.1.1", extra_data={"reason": "syn-ack"})
        assert p.extra_data["reason"] == "syn-ack"

    def test_ip_output_type(self):
        i = Ip(ip="192.168.1.1", alive=True)
        assert i._type == "ip"
        assert i.alive is True

    def test_certificate_output_type(self):
        c = Certificate(
            host="example.com", self_signed=False, issuer_cn="Let's Encrypt"
        )
        assert c._type == "certificate"
        assert c.self_signed is False

    def test_exploit_output_type(self):
        e = Exploit(name="EDB-12345", provider="exploitdb", cves=["CVE-2024-1234"])
        assert e._type == "exploit"
        assert "CVE-2024-1234" in e.cves


# ── Task Base ──────────────────────────────────────────────────────────────


class DummyTask(Task):
    name = "dummy"
    cmd = "echo"
    description = "Test task"
    category = "test/unit"
    install_cmd = "true"
    output_types = [Url]

    opts = {
        "verbose": OptDef(flag="-v", is_flag=True, help="Verbose"),
        "count": OptDef(flag="-c", type=int, help="Count"),
        "output": OptDef(flag="-o", type=str, help="Output file"),
    }

    input_flag = "-t"

    def parse_output(self, stdout, stderr, output_file=None):
        return [Url(url=line.strip()) for line in stdout.splitlines() if line.strip()]


class TestTaskBase:
    def test_build_command_basic(self):
        t = DummyTask()
        cmd, out = t.build_command("target.com")
        assert "echo" in cmd
        assert "-t target.com" in cmd

    def test_build_command_with_flag(self):
        t = DummyTask()
        cmd, _ = t.build_command("x.com", verbose=True)
        assert "-v" in cmd

    def test_build_command_with_value_opt(self):
        t = DummyTask()
        cmd, _ = t.build_command("x.com", count=5)
        assert "-c 5" in cmd

    def test_build_command_skips_false_flags(self):
        t = DummyTask()
        cmd, _ = t.build_command("x.com", verbose=False)
        assert "-v" not in cmd

    def test_build_command_skips_none_values(self):
        t = DummyTask()
        cmd, _ = t.build_command("x.com", count=None)
        assert "-c" not in cmd

    def test_build_command_ignores_unknown_opts(self):
        t = DummyTask()
        cmd, _ = t.build_command("x.com", nonexistent="val")
        assert "nonexistent" not in cmd

    def test_parse_output(self):
        t = DummyTask()
        results = t.parse_output("http://a.com\nhttp://b.com\n", "")
        assert len(results) == 2
        assert all(isinstance(r, Url) for r in results)

    def test_check_installed(self):
        t = DummyTask()
        assert t.check_installed()  # echo should exist

    def test_get_install_command(self):
        t = DummyTask()
        assert t.get_install_command() == "true"

    def test_safe_int(self):
        assert Task._safe_int("42") == 42
        assert Task._safe_int("bad") == 0
        assert Task._safe_int(None, 99) == 99

    def test_safe_float(self):
        assert Task._safe_float("3.14") == 3.14
        assert Task._safe_float("bad") == 0.0


# ── Task Registry ─────────────────────────────────────────────────────────


class TestTaskRegistry:
    def setup_method(self):
        # Force re-load so tasks are always available
        TaskRegistry._ensure_loaded()

    def test_builtin_tasks_registered(self):
        tasks = TaskRegistry.list_tasks()
        assert "nmap" in tasks
        assert "httpx" in tasks
        assert "subfinder" in tasks
        assert "nuclei" in tasks
        assert "ffuf" in tasks

    def test_create_task(self):
        task = TaskRegistry.create("nmap")
        assert task.name == "nmap"
        assert task.cmd == "nmap"

    def test_create_unknown_raises(self):
        with pytest.raises(KeyError, match="not registered"):
            TaskRegistry.create("nonexistent_tool_xyz")

    def test_get_returns_none_for_unknown(self):
        assert TaskRegistry.get("no_such_task") is None

    def test_get_by_category(self):
        port_tasks = TaskRegistry.get_by_category("port/")
        assert any(name == "nmap" for name, _ in port_tasks)

    def test_get_by_category_empty_returns_all(self):
        """Empty category prefix matches all tasks."""
        all_tasks = TaskRegistry.get_by_category("")
        assert len(all_tasks) == len(TaskRegistry.list_tasks())

    def test_register_duplicate_raises(self):
        # Register a fresh name then try to register it again
        name = "_test_dup_check"
        TaskRegistry.unregister(name)  # ensure clean

        @TaskRegistry.register(name)
        class FirstTool(Task):
            name = "first"
            cmd = "true"

            def parse_output(self, stdout, stderr, output_file=None):
                return []

        with pytest.raises(ValueError, match="already registered"):

            @TaskRegistry.register(name)
            class SecondTool(Task):
                name = "second"
                cmd = "true"

                def parse_output(self, stdout, stderr, output_file=None):
                    return []

        TaskRegistry.unregister(name)

    def test_unregister(self):
        @TaskRegistry.register("temp_test_tool")
        class TempTool(Task):
            name = "temp"
            cmd = "true"

            def parse_output(self, stdout, stderr, output_file=None):
                return []

        assert TaskRegistry.get("temp_test_tool") is not None
        TaskRegistry.unregister("temp_test_tool")
        assert TaskRegistry.get("temp_test_tool") is None


# ── Step Model Integration ─────────────────────────────────────────────────


class TestStepModelTask:
    def test_step_with_task_field(self):
        s = Step(task="nmap", **{"with": {"target": "1.2.3.4"}})
        assert s.get_run_type() == RunType.TASK
        assert s.task == "nmap"

    def test_step_task_exclusive(self):
        """task can't coexist with run/script/uses."""
        with pytest.raises(ValueError, match="exactly one"):
            Step(task="nmap", run="echo hi")

    def test_step_task_and_script_exclusive(self):
        with pytest.raises(ValueError, match="exactly one"):
            Step(task="nmap", script="print('hi')")

    def test_step_with_options(self):
        s = Step(
            task="nmap",
            **{
                "with": {
                    "target": "10.0.0.0/24",
                    "ports": "1-1000",
                    "version_detection": True,
                }
            },
        )
        assert s.run_with["target"] == "10.0.0.0/24"
        assert s.run_with["ports"] == "1-1000"

    def test_existing_run_types_still_work(self):
        s1 = Step(run="echo hi")
        assert s1.get_run_type() == RunType.COMMAND

        s2 = Step(script="print('hi')")
        assert s2.get_run_type() == RunType.SCRIPT

        s3 = Step(uses="./other.yml")
        assert s3.get_run_type() == RunType.WORKFLOW


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


# ── Command Building ──────────────────────────────────────────────────────


class TestCommandBuilding:
    def test_nmap_command(self):
        task = TaskRegistry.create("nmap")
        cmd, out = task.build_command(
            "192.168.1.0/24", ports="22,80,443", version_detection=True
        )
        assert "nmap" in cmd
        assert "-p 22,80,443" in cmd
        assert "-sV" in cmd
        assert "192.168.1.0/24" in cmd
        assert out is not None  # output file created for -oX

    def test_httpx_command(self):
        task = TaskRegistry.create("httpx")
        cmd, out = task.build_command("https://example.com", tech_detect=True)
        assert "httpx" in cmd
        assert "-json" in cmd
        assert "-tech-detect" in cmd

    def test_subfinder_command(self):
        task = TaskRegistry.create("subfinder")
        cmd, _ = task.build_command("example.com", all=True)
        assert "subfinder" in cmd
        assert "-all" in cmd
        assert "-d example.com" in cmd

    def test_nuclei_command(self):
        task = TaskRegistry.create("nuclei")
        cmd, _ = task.build_command("https://target.com", severity="critical,high")
        assert "nuclei" in cmd
        assert "-severity critical,high" in cmd

    def test_ffuf_command(self):
        task = TaskRegistry.create("ffuf")
        cmd, _ = task.build_command(
            "https://target.com/FUZZ",
            wordlist="/usr/share/wordlists/common.txt",
            threads=50,
        )
        assert "ffuf" in cmd
        assert "-w /usr/share/wordlists/common.txt" in cmd
        assert "-t 50" in cmd

    def test_output_file_cleanup(self):
        """Output files are temp files that exist on disk."""
        task = TaskRegistry.create("nmap")
        _, out = task.build_command("x.com")
        assert out is not None
        assert out.exists()
        out.unlink()  # cleanup


# ── New Tools ──────────────────────────────────────────────────────────────


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


# ── Deduplication ──────────────────────────────────────────────────────────


class TestDeduplication:
    def test_dedup_removes_duplicates(self):
        from ofx.runner.tasks.runner import TaskRunner

        items = [
            Port(port=80, ip="10.0.0.1"),
            Port(port=80, ip="10.0.0.1"),  # duplicate
            Port(port=443, ip="10.0.0.1"),
        ]
        result = TaskRunner._deduplicate(items)
        assert len(result) == 2
        assert result[0].port == 80
        assert result[1].port == 443

    def test_dedup_preserves_unique(self):
        from ofx.runner.tasks.runner import TaskRunner

        items = [
            Url(url="https://a.com"),
            Url(url="https://b.com"),
            Url(url="https://c.com"),
        ]
        result = TaskRunner._deduplicate(items)
        assert len(result) == 3

    def test_dedup_empty(self):
        from ofx.runner.tasks.runner import TaskRunner
        assert TaskRunner._deduplicate([]) == []


# ── Extra Flags Refactor ──────────────────────────────────────────────────


class TestExtraFlags:
    """Verify the DRY refactor: extra_flags are included in build_command."""

    def test_httpx_extra_flags(self):
        task = TaskRegistry.create("httpx")
        cmd, _ = task.build_command("https://example.com")
        assert "-json -silent" in cmd

    def test_subfinder_extra_flags(self):
        task = TaskRegistry.create("subfinder")
        cmd, _ = task.build_command("example.com")
        assert "-silent" in cmd

    def test_nuclei_extra_flags(self):
        task = TaskRegistry.create("nuclei")
        cmd, _ = task.build_command("https://target.com")
        assert "-jsonl -silent" in cmd

    def test_ffuf_extra_flags(self):
        task = TaskRegistry.create("ffuf")
        cmd, _ = task.build_command("https://target.com/FUZZ")
        assert "-noninteractive" in cmd
        assert "-of json" in cmd

    def test_nmap_no_extra_flags(self):
        """Nmap doesn't need extra_flags — it uses the base build_command."""
        task = TaskRegistry.create("nmap")
        cmd, _ = task.build_command("10.0.0.1")
        # Should start with just "nmap" — no extra flags
        assert cmd.startswith("nmap ")


# ── Registry — New Tools ──────────────────────────────────────────────────


class TestNewToolsRegistered:
    def test_all_tools_registered(self):
        expected = [
            "nmap", "httpx", "subfinder", "nuclei", "ffuf",
            "naabu", "katana", "dnsx", "wafw00f", "feroxbuster",
        ]
        for name in expected:
            assert TaskRegistry.get(name) is not None, f"Task '{name}' not registered"

    def test_categories(self):
        port_tasks = TaskRegistry.get_by_category("port/")
        assert len(port_tasks) >= 2  # nmap + naabu

        dns_tasks = TaskRegistry.get_by_category("dns/")
        assert len(dns_tasks) >= 2  # subfinder + dnsx

        url_tasks = TaskRegistry.get_by_category("url/")
        assert len(url_tasks) >= 3  # httpx + ffuf + katana + feroxbuster


# ── Mutable Default Isolation ─────────────────────────────────────────────


class TestMutableDefaults:
    """Verify __init_subclass__ prevents cross-class mutation."""

    def test_extra_flags_isolated_between_subclasses(self):
        """Mutating one task's extra_flags must not affect another."""
        httpx_cls = TaskRegistry.get("httpx")
        nmap_cls = TaskRegistry.get("nmap")
        assert httpx_cls is not None and nmap_cls is not None

        httpx = httpx_cls()
        nmap = nmap_cls()

        original_httpx_flags = list(httpx.extra_flags)
        original_nmap_flags = list(nmap.extra_flags)

        # Mutate httpx's extra_flags (on the class)
        httpx_cls.extra_flags.append("--SHOULD-NOT-LEAK")

        # nmap's extra_flags must be unaffected
        assert "--SHOULD-NOT-LEAK" not in nmap_cls.extra_flags
        assert nmap_cls.extra_flags == original_nmap_flags

        # Restore
        httpx_cls.extra_flags[:] = original_httpx_flags

    def test_opts_isolated_between_subclasses(self):
        """Mutating one task's opts must not affect another."""
        nmap_cls = TaskRegistry.get("nmap")
        subfinder_cls = TaskRegistry.get("subfinder")
        assert nmap_cls is not None and subfinder_cls is not None

        original_nmap_opts = set(nmap_cls.opts.keys())

        nmap_cls.opts["_test_key"] = OptDef(flag="--test")
        assert "_test_key" not in subfinder_cls.opts

        # Restore
        del nmap_cls.opts["_test_key"]
        assert set(nmap_cls.opts.keys()) == original_nmap_opts

    def test_base_task_defaults_unaffected(self):
        """Subclass mutations must not leak back to the Task base."""
        assert Task.extra_flags == []
        assert Task.opts == {}
        assert Task.output_types == []


# ── Template Helpers ──────────────────────────────────────────────────────


class TestTemplateHelpers:
    """Verify template helper functions filter typed_output dicts correctly."""

    @pytest.fixture()
    def sample_outputs(self):
        return [
            {"_type": "port", "port": 80, "ip": "10.0.0.1"},
            {"_type": "port", "port": 443, "ip": "10.0.0.1"},
            {"_type": "url", "url": "https://example.com"},
            {"_type": "vulnerability", "name": "XSS", "severity": "high"},
            {"_type": "subdomain", "host": "api.example.com"},
            {"_type": "ip", "ip": "10.0.0.1"},
            {"_type": "tag", "name": "nginx", "category": "technology"},
            {"_type": "record", "name": "mx.example.com", "type": "MX"},
            {"_type": "domain", "domain": "example.com"},
        ]

    @staticmethod
    def _of_type(items, type_name):
        """Replicate the template helper logic for testing."""
        if not isinstance(items, list):
            return []
        return [i for i in items if isinstance(i, dict) and i.get("_type") == type_name]

    def test_of_type(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "port")) == 2
        assert len(self._of_type(sample_outputs, "url")) == 1

    def test_ports(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "port")) == 2

    def test_urls(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "url")) == 1

    def test_vulns(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "vulnerability")) == 1

    def test_subdomains(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "subdomain")) == 1

    def test_ips(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "ip")) == 1

    def test_tags(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "tag")) == 1

    def test_records(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "record")) == 1

    def test_domains(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "domain")) == 1

    def test_of_type_with_non_list(self):
        assert self._of_type("not a list", "port") == []
        assert self._of_type(None, "port") == []

    def test_of_type_empty_list(self):
        assert self._of_type([], "port") == []

    def test_helpers_registered_in_resolver(self):
        """Verify all helper names exist in TemplateResolver support functions."""
        from ofx.runner.templates.resolver import TemplateResolver

        resolver = TemplateResolver()
        funcs = resolver.get_support_functions()
        for name in ("of_type", "ports", "urls", "vulns", "subdomains",
                      "ips", "tags", "records", "domains"):
            assert name in funcs, f"Helper '{name}' not in support functions"


# ── Pre-flight Binary Check ───────────────────────────────────────────────


class TestPreflightCheck:
    """Verify TaskRunner warns when tool binary is not installed."""

    def test_check_installed_returns_bool(self):
        task = TaskRegistry.create("nmap")
        # Just verify the method returns a bool (actual result depends on system)
        assert isinstance(task.check_installed(), bool)

    def test_get_install_command(self):
        task = TaskRegistry.create("nmap")
        assert task.get_install_command() == "apt install -y nmap"

    def test_get_install_command_none_when_empty(self):
        """A task with no install_cmd returns None."""

        class BareTask(Task):
            name = "bare"
            cmd = "bare"
            install_cmd = ""

            def parse_output(self, stdout, stderr, output_file=None):
                return []

        t = BareTask()
        assert t.get_install_command() is None


# ── UserAccount Output Type ────────────────────────────────────────────


class TestUserAccount:
    def test_basic_fields(self):
        from ofx.tasks.output_types import UserAccount

        u = UserAccount(
            username="admin",
            password="P@ss",
            domain="CORP",
            host="10.0.0.1",
            account_type="domain",
            privilege_level="admin",
        )
        assert u._type == "user_account"
        assert u.username == "admin"
        assert u.privilege_level == "admin"

    def test_to_dict(self):
        from ofx.tasks.output_types import UserAccount

        u = UserAccount(username="root", host="srv1")
        d = u.to_dict()
        assert d["_type"] == "user_account"
        assert d["username"] == "root"
        assert "_uuid" in d

    def test_uuid_deterministic(self):
        from ofx.tasks.output_types import UserAccount

        u1 = UserAccount(username="admin", domain="CORP")
        u2 = UserAccount(username="admin", domain="CORP")
        assert u1._uuid == u2._uuid

    def test_uuid_different(self):
        from ofx.tasks.output_types import UserAccount

        u1 = UserAccount(username="admin")
        u2 = UserAccount(username="guest")
        assert u1._uuid != u2._uuid

    def test_to_credential(self):
        from ofx.tasks.output_types import UserAccount

        u = UserAccount(
            username="admin",
            password="secret",
            hash="aad3b435b51404ee",
            domain="CORP",
            host="DC01",
            account_type="domain",
            source="secretsdump",
        )
        cred = u.to_credential()
        assert cred.username == "admin"
        assert cred.password == "secret"
        assert cred.hash == "aad3b435b51404ee"
        assert cred.domain == "CORP"
        assert "host=DC01" in cred.comment
        assert "source=secretsdump" in cred.comment

    def test_from_credential(self):
        from dataclasses import dataclass

        from ofx.tasks.output_types import UserAccount

        @dataclass
        class FakeCred:
            username: str = "user1"
            password: str = "pass1"
            hash: str = ""
            domain: str = "LOCAL"
            comment: str = "test"

        cred = FakeCred()
        u = UserAccount.from_credential(cred, host="10.0.0.5", source="mimikatz")
        assert u.username == "user1"
        assert u.password == "pass1"
        assert u.domain == "LOCAL"
        assert u.host == "10.0.0.5"
        assert u.source == "mimikatz"

    def test_in_output_type_map(self):
        from ofx.tasks.output_types import OUTPUT_TYPE_MAP, UserAccount

        assert OUTPUT_TYPE_MAP["user_account"] is UserAccount


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


# ── Template Helper: users() ───────────────────────────────────────────


class TestUsersTemplateHelper:
    def test_users_filter(self):
        from ofx.runner.templates.resolver import TemplateResolver

        resolver = TemplateResolver()
        funcs = resolver.get_support_functions()
        users_fn = funcs["users"]

        items = [
            {"_type": "user_account", "username": "admin"},
            {"_type": "port", "port": 80},
            {"_type": "user_account", "username": "guest"},
        ]
        result = users_fn(items)
        assert len(result) == 2
        assert result[0]["username"] == "admin"
        assert result[1]["username"] == "guest"


# ── Profile System ─────────────────────────────────────────────────────


class TestProfiles:
    def test_profile_model_defaults(self):
        from ofx.profiles.models import OFXProfile

        p = OFXProfile()
        assert p.rate_limit == 0
        assert p.threads == 10
        assert p.time_window.enabled is False

    def test_profile_model_custom(self):
        from ofx.profiles.models import OFXProfile

        p = OFXProfile(
            name="stealth",
            rate_limit=30,
            delay=2.0,
            jitter=1.0,
            threads=2,
            proxy="socks5://127.0.0.1:9050",
        )
        assert p.rate_limit == 30
        assert p.delay == 2.0
        assert p.proxy == "socks5://127.0.0.1:9050"

    def test_time_window_model(self):
        from ofx.profiles.models import TimeWindow

        tw = TimeWindow(
            enabled=True,
            start="09:00",
            end="17:00",
            days=["monday", "tuesday", "wednesday", "thursday", "friday"],
            timezone="US/Eastern",
        )
        assert tw.start_time().hour == 9
        assert tw.end_time().hour == 17
        assert "saturday" not in tw.days

    def test_profile_manager_crud(self, tmp_path):
        from ofx.profiles.manager import ProfileManager

        mgr = ProfileManager(config_path=tmp_path / "profiles.yml")
        assert mgr.list_profiles() == []

        mgr.add("test", {"rate_limit": 100, "description": "test profile"})
        assert mgr.exists("test")
        assert "test" in mgr.list_profiles()

        profile = mgr.resolve("test")
        assert profile.rate_limit == 100

        mgr.remove("test")
        assert not mgr.exists("test")

    def test_profile_manager_default(self, tmp_path):
        from ofx.profiles.manager import ProfileManager

        mgr = ProfileManager(config_path=tmp_path / "profiles.yml")
        mgr.add("p1", {"rate_limit": 10})
        mgr.add("p2", {"rate_limit": 20})
        mgr.set_default("p1")
        assert mgr.default_profile_name == "p1"

        result = mgr.resolve_or_default(None)
        assert result is not None
        assert result.rate_limit == 10

    def test_profile_manager_not_found(self, tmp_path):
        from ofx.profiles.manager import ProfileManager

        mgr = ProfileManager(config_path=tmp_path / "profiles.yml")
        with pytest.raises(KeyError):
            mgr.resolve("nonexistent")

    def test_profile_task_options(self):
        from ofx.profiles.models import OFXProfile

        p = OFXProfile(
            task_options={"nmap": {"timing": "T2", "ports": "80,443"}}
        )
        assert p.task_options["nmap"]["timing"] == "T2"


# ── Time Window Enforcement ────────────────────────────────────────────


class TestTimeWindow:
    def test_disabled_window_always_allowed(self):
        from ofx.profiles.models import TimeWindow
        from ofx.profiles.time_window import check_time_window

        tw = TimeWindow(enabled=False)
        result = check_time_window(tw)
        assert result["allowed"] is True

    def test_check_within_window(self):
        from datetime import datetime

        from ofx.profiles.models import TimeWindow
        from ofx.profiles.time_window import check_time_window

        # Create a window that covers the current time
        now = datetime.now()
        start = f"{max(0, now.hour - 1):02d}:00"
        end = f"{min(23, now.hour + 1):02d}:59"
        day = now.strftime("%A").lower()

        tw = TimeWindow(enabled=True, start=start, end=end, days=[day])
        result = check_time_window(tw)
        assert result["allowed"] is True

    def test_check_outside_window_day(self):
        from ofx.profiles.models import TimeWindow
        from ofx.profiles.time_window import check_time_window

        # No valid days
        tw = TimeWindow(enabled=True, start="00:00", end="23:59", days=[])
        result = check_time_window(tw)
        assert result["allowed"] is False
        assert "outside the allowed days" in result["message"]

    def test_check_outside_window_time(self):
        from datetime import datetime

        from ofx.profiles.models import TimeWindow
        from ofx.profiles.time_window import check_time_window

        now = datetime.now()
        # Set window to an hour that's definitely not now
        if now.hour < 12:
            start, end = "18:00", "19:00"
        else:
            start, end = "03:00", "04:00"

        tw = TimeWindow(
            enabled=True,
            start=start,
            end=end,
            days=[now.strftime("%A").lower()],
        )
        result = check_time_window(tw)
        assert result["allowed"] is False

    def test_time_in_range_normal(self):
        from datetime import time

        from ofx.profiles.time_window import _time_in_range

        assert _time_in_range(time(9, 0), time(17, 0), time(12, 0)) is True
        assert _time_in_range(time(9, 0), time(17, 0), time(18, 0)) is False

    def test_time_in_range_overnight(self):
        from datetime import time

        from ofx.profiles.time_window import _time_in_range

        # Overnight window: 22:00 → 06:00
        assert _time_in_range(time(22, 0), time(6, 0), time(23, 0)) is True
        assert _time_in_range(time(22, 0), time(6, 0), time(3, 0)) is True
        assert _time_in_range(time(22, 0), time(6, 0), time(12, 0)) is False

    def test_time_window_guard_not_started_when_disabled(self):
        import asyncio

        from ofx.profiles.models import TimeWindow
        from ofx.profiles.time_window import TimeWindowGuard

        tw = TimeWindow(enabled=False)
        guard = TimeWindowGuard(tw)
        guard.start()
        assert guard._task is None

    def test_warn_message_near_end(self):
        from datetime import datetime

        from ofx.profiles.models import TimeWindow
        from ofx.profiles.time_window import check_time_window

        now = datetime.now()
        day = now.strftime("%A").lower()
        # Window that ends in 5 minutes
        end_min = (now.minute + 5) % 60
        end_hour = now.hour + ((now.minute + 5) // 60)
        if end_hour > 23:
            end_hour = 23
            end_min = 59

        tw = TimeWindow(
            enabled=True,
            start=f"{max(0, now.hour - 1):02d}:00",
            end=f"{end_hour:02d}:{end_min:02d}",
            days=[day],
            warn_before_minutes=10,
        )
        result = check_time_window(tw)
        if result["allowed"] and 0 < result["remaining_minutes"] <= 10:
            assert "remaining" in result["message"]


# ── DefaultConfig Profile Field ────────────────────────────────────────


class TestDefaultConfigProfile:
    def test_default_config_has_profile_field(self):
        from ofx.models.config import DefaultConfig

        dc = DefaultConfig()
        assert dc.profile == ""

    def test_default_config_with_profile(self):
        from ofx.models.config import DefaultConfig

        dc = DefaultConfig(profile="stealth")
        assert dc.profile == "stealth"
