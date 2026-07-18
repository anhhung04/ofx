"""Tests for individual tool parsers, parse_line, streaming detection, and output edge cases."""

import json

from ofx.tasks import (
    Subdomain,
    TaskRegistry,
    Vulnerability,
)
from ofx.tasks.output_types import (
    Ip,
    Severity,
)

class TestDnsxParser:
    def test_parse_jsonl(self):
        lines = [
            json.dumps(
                {
                    "host": "example.com",
                    "a": ["93.184.216.34"],
                    "cname": ["cdn.example.com"],
                    "mx": ["mail.example.com"],
                }
            ),
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
        assert len(records) == 2

    def test_command_building(self):
        task = TaskRegistry.create("dnsx")
        cmd, _ = task.build_command("example.com", a=True, cname=True, threads=50)
        assert "dnsx" in cmd
        assert "-json" in cmd
        assert "-a" in cmd
        assert "-cname" in cmd
        assert "-t 50" in cmd

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
            {
                "type": "AAAA",
                "name": "ipv6.example.com",
                "address": "2606:2800:220:1::",
            },
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

class TestSubfinderParser:
    def test_parse_output(self):
        stdout = "api.example.com\nwww.example.com\nmail.example.com\n"
        task = TaskRegistry.create("subfinder")
        results = task.parse_output(stdout, "")
        assert len(results) == 3
        assert all(isinstance(r, Subdomain) for r in results)
        assert results[0].host == "api.example.com"
        assert results[0].domain == "example.com"

class TestAsnmapParser:
    def test_parse_line(self):
        task = TaskRegistry.create("asnmap")

        results = task.parse_line(
            json.dumps(
                {
                    "input": "AS13335",
                    "as_range": "104.16.0.0/13",
                    "as_number": "13335",
                    "as_name": "CLOUDFLARENET",
                    "as_country": "US",
                }
            )
        )

        assert len(results) == 1
        assert isinstance(results[0], Ip)
        assert results[0].ip == "104.16.0.0/13"
        assert results[0].host == "AS13335"
        assert results[0].extra_data == {
            "as_number": "13335",
            "as_name": "CLOUDFLARENET",
            "as_country": "US",
        }

class TestAmassParser:
    def test_amass_metadata(self):
        task = TaskRegistry.create("amass")
        assert task.name == "amass"
        assert task.cmd == "amass"
        assert task.category == "dns/recon"
        assert Subdomain in task.output_types
        assert "go install" in task.install_cmd
        assert "/amass/v5/" in task.install_cmd

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
        assert "amass -version" in cmd
        assert "amass enum" in cmd
        assert "amass subs" in cmd
        assert "-passive" in cmd
        assert "-brute" in cmd
        assert "-timeout 30" in cmd
        assert "-d example.com" in cmd
        assert out_file is not None
        assert out_file.suffix == ".txt"
        if out_file and out_file.exists():
            out_file.unlink()

    def test_amass_build_command_active(self):
        task = TaskRegistry.create("amass")
        cmd, _ = task.build_command("example.com", active=True)
        assert "-active" in cmd
        assert "-passive" not in cmd

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

class TestSubzyParser:
    def test_subzy_metadata(self):
        task = TaskRegistry.create("subzy")
        assert task.name == "subzy"
        assert task.cmd == "subzy"
        assert task.category == "vuln/takeover"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_subzy_parse_output(self):
        stdout = "\n".join(
            [
                "[NOT VULNERABLE] safe.example.com",
                "[VULNERABLE] dangling.example.com - Service: GitHub Pages - CNAME pointing to unregistered github.io",
                "[VULNERABLE] old.example.com - Heroku",
            ]
        )
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
