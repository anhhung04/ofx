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
        assert len(OUTPUT_TYPE_MAP) == 10

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
