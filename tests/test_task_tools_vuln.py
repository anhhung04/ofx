"""Tests for individual tool parsers, parse_line, streaming detection, and output edge cases."""

import json
import xml.etree.ElementTree as ET

from ofx.tasks import (
    TaskRegistry,
    Url,
    Vulnerability,
)
from ofx.tasks.output_types import (
    Severity,
    Tag,
)

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
        assert vulns[1].id == "0"

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
        cmd, _ = task.build_command(
            "https://example.com", enumerate="vp,vt", stealthy=True
        )
        assert "wpscan" in cmd
        assert "--format" in cmd
        assert "json" in cmd
        assert "--url https://example.com" in cmd
        assert "-e vp,vt" in cmd
        assert "--stealthy" in cmd

    def test_registration(self):
        task = TaskRegistry.create("wpscan")
        assert task.name == "wpscan"

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

class TestDalfoxParser:
    def test_parse_output(self):
        lines = [
            json.dumps(
                {
                    "type": "vuln",
                    "data": "[POC] reflected XSS found",
                    "proof": "<script>alert(1)</script>",
                    "param": "q",
                    "payload": "<script>alert(1)</script>",
                    "method": "GET",
                    "url": "https://example.com/search?q=test",
                }
            ),
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

class TestCommixParser:
    def test_commix_metadata(self):
        task = TaskRegistry.create("commix")
        assert task.name == "commix"
        assert task.cmd == "commix"
        assert task.category == "vuln/injection"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_commix_parse_output(self):
        stdout = "\n".join(
            [
                "[*] Testing connection to the target URL...",
                "[*] Checking if the target is protected by some kind of WAF/IPS...",
                "The ('classic') technique appears to be injectable.",
                "The ('eval-based') technique appears to be injectable.",
                "The parameter 'id' is vulnerable.",
                "The ('time-based') technique appears to be injectable.",
                "The parameter 'name' is vulnerable.",
            ]
        )
        task = TaskRegistry.create("commix")
        results = task.parse_output(stdout, "")
        assert len(results) == 2
        assert all(isinstance(r, Vulnerability) for r in results)
        assert results[0].name == "Command Injection"
        assert results[0].matched_at == "id"
        assert results[0].severity == Severity.CRITICAL
        assert "classic" in results[0].description
        assert "eval-based" in results[0].description
        assert results[1].matched_at == "name"
        assert "time-based" in results[1].description

    def test_commix_parse_empty(self):
        task = TaskRegistry.create("commix")
        assert task.parse_output("", "") == []

    def test_commix_parse_no_vuln(self):
        stdout = "\n".join(
            [
                "[*] Testing connection to the target URL...",
                "[*] Target does not appear to be injectable.",
            ]
        )
        task = TaskRegistry.create("commix")
        assert task.parse_output(stdout, "") == []

class TestCrlfuzzParser:
    def test_crlfuzz_metadata(self):
        task = TaskRegistry.create("crlfuzz")
        assert task.name == "crlfuzz"
        assert task.cmd == "crlfuzz"
        assert task.category == "vuln/injection"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_crlfuzz_parse_output(self):
        stdout = "\n".join(
            [
                "https://example.com/path%0d%0aInjected-Header:true",
                "https://example.com/other%0d%0aSet-Cookie:evil",
            ]
        )
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
            certs=[
                {
                    "subject": "/CN=example.com/O=Example Inc",
                    "issuer": "/CN=DigiCert/O=DigiCert Inc",
                    "not-valid-before": "Jan  1 00:00:00 2024 GMT",
                    "not-valid-after": "Dec 31 23:59:59 2025 GMT",
                    "self-signed": "false",
                    "fingerprint": "AA:BB:CC:DD",
                    "altnames": "example.com, www.example.com",
                }
            ],
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
        assert len(certs) == 1
        assert certs[0].subject_cn == "2025-01-01"
        assert certs[0].host == "93.184.216.34:443"
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
        cmd, out_file = task.build_command(
            "example.com:443", protocols=True, vulnerabilities=True
        )
        assert "testssl.sh" in cmd
        assert "-p" in cmd
        assert "-U" in cmd
        assert "example.com:443" in cmd
        assert out_file is not None
        if out_file and out_file.exists():
            out_file.unlink()

    def test_registration(self):
        task = TaskRegistry.create("testssl")
        assert task.name == "testssl"

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
