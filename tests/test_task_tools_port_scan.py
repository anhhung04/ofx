"""Tests for individual tool parsers, parse_line, streaming detection, and output edge cases."""

import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from ofx.tasks import (
    Port,
    TaskRegistry,
)
from ofx.tasks.output_types import (
    Ip,
    Tag,
)

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
        data = json.dumps(
            [
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
            ]
        )
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
        data = json.dumps(
            [
                {
                    "ip": "10.0.0.1",
                    "ports": [
                        {
                            "port": 80,
                            "proto": "tcp",
                            "status": "open",
                            "service": {"name": "http"},
                        },
                    ],
                },
            ]
        )
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

class TestRustscanParser:
    def test_rustscan_metadata(self):
        task = TaskRegistry.create("rustscan")
        assert task.name == "rustscan"
        assert task.cmd == "rustscan"
        assert task.category == "port/scan"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_rustscan_parse_output_open_format(self):
        stdout = "\n".join(
            [
                "Open 10.0.0.1:22",
                "Open 10.0.0.1:80",
                "Open 10.0.0.1:443",
            ]
        )
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
        line = json.dumps(
            {
                "ip": "192.168.1.1",
                "host": "web.local",
                "port": 80,
                "protocol": "tcp",
                "service": "http",
                "version": "2.4.51",
                "product": "Apache",
                "banner": "Apache/2.4.51 (Ubuntu)",
                "cpe": "cpe:/a:apache:http_server:2.4.51",
            }
        )
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
        stdout = "\n".join(
            [
                json.dumps({"ip": "10.0.0.1", "port": 22, "service": "ssh"}),
                json.dumps(
                    {
                        "ip": "10.0.0.1",
                        "port": 80,
                        "service": "http",
                        "product": "nginx",
                    }
                ),
                "[info] scan complete",
            ]
        )
        results = task.parse_output(stdout, "")
        ports = [r for r in results if isinstance(r, Port)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(ports) == 2
        assert len(tags) == 1

    def test_nerva_parse_output_file(self, tmp_path):
        task = TaskRegistry.create("nerva")
        f = tmp_path / "out.jsonl"
        f.write_text(
            json.dumps(
                {
                    "ip": "10.0.0.1",
                    "port": 3306,
                    "service": "mysql",
                    "product": "MySQL",
                    "version": "8.0",
                }
            )
        )
        results = task.parse_output("", "", output_file=f)
        assert len(results) == 2
        assert results[0].port == 3306
        assert results[1].name == "MySQL"

    def test_nerva_parse_empty(self):
        task = TaskRegistry.create("nerva")
        assert task.parse_output("", "") == []

    def test_nerva_streaming(self):
        task = TaskRegistry.create("nerva")
        assert task.supports_streaming is True

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
