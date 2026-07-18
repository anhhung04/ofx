"""Tests for individual tool parsers, parse_line, streaming detection, and output edge cases."""

import json

from ofx.tasks import (
    Subdomain,
    TaskRegistry,
    Vulnerability,
)
from ofx.tasks.output_types import (
    Severity,
    Tag,
    UserAccount,
)

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

class TestMaigretParser:
    def test_parse_output(self):
        lines = [
            json.dumps(
                {
                    "siteName": "GitHub",
                    "url_user": "https://github.com/testuser",
                    "status": "Claimed",
                    "username": "testuser",
                }
            ),
        ]
        task = TaskRegistry.create("maigret")
        results = task.parse_output("\n".join(lines), "")
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
        assert out_file is not None
        if out_file and out_file.exists():
            out_file.unlink()

    def test_registration(self):
        task = TaskRegistry.create("h8mail")
        assert task.name == "h8mail"

class TestHoleheParser:
    def test_holehe_metadata(self):
        task = TaskRegistry.create("holehe")
        assert task.name == "holehe"
        assert task.cmd == "holehe"
        assert task.category == "user/recon/email"
        assert UserAccount in task.output_types
        assert "holehe" in task.install_cmd

    def test_holehe_parse_output(self):
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
        cmd, out_file = task.build_command(
            "user@example.com", only_used=True, timeout=30
        )
        assert "holehe" in cmd
        assert "--no-color" in cmd
        assert "--only-used" in cmd
        assert "-t 30" in cmd
        assert "user@example.com" in cmd
        assert out_file is None

class TestTheHarvesterParser:
    def test_theharvester_metadata(self):
        task = TaskRegistry.create("theharvester")
        assert task.name == "theharvester"
        assert task.cmd == "theHarvester"
        assert task.category == "osint/recon"
        assert Subdomain in task.output_types
        assert UserAccount in task.output_types
        assert "theHarvester" in task.install_cmd

    def test_theharvester_parse_xml(self, tmp_path):
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
        stdout = "[*] Searching Google...\nuser1@example.com\nuser2@example.com\n"
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

class TestTrufflehogParser:
    def test_parse_output(self):
        lines = [
            json.dumps(
                {
                    "DetectorName": "AWS",
                    "Verified": True,
                    "Raw": "AKIAIOSFODNN7EXAMPLE",
                    "SourceMetadata": {
                        "Data": {"Filesystem": {"file": "secrets.txt"}},
                    },
                }
            ),
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

    def test_bare_domain_normalized_to_https(self):
        task = TaskRegistry.create("trufflehog")
        cmd, _ = task.build_command("nhi.cocay.me")
        assert "https://nhi.cocay.me" in cmd

    def test_bare_domain_with_path_normalized(self):
        task = TaskRegistry.create("trufflehog")
        cmd, _ = task.build_command("github.com/org/repo")
        assert "https://github.com/org/repo" in cmd

    def test_https_url_unchanged(self):
        task = TaskRegistry.create("trufflehog")
        cmd, _ = task.build_command("https://github.com/org/repo")
        assert "https://github.com/org/repo" in cmd

    def test_ssh_uri_unchanged(self):
        task = TaskRegistry.create("trufflehog")
        cmd, _ = task.build_command("git@github.com:org/repo.git")
        assert "git@github.com:org/repo.git" in cmd

    def test_filesystem_mode_skips_normalization(self):
        task = TaskRegistry.create("trufflehog")
        cmd, _ = task.build_command("nhi.cocay.me", mode="filesystem")
        assert "https://" not in cmd
        assert "nhi.cocay.me" in cmd

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
        stdout = "\n".join(
            [
                "5d41402abc4b2a76b9719d911017c592",
                "  MD5  HC: 0  JtR: raw-md5",
                "  MD4  HC: 900  JtR: raw-md4",
            ]
        )
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

class TestHashidParser:
    def test_hashid_metadata(self):
        task = TaskRegistry.create("hashid")
        assert task.name == "hashid"
        assert task.cmd == "hashid"
        assert task.category == "crypto/identify"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_hashid_parse_output(self):
        stdout = "\n".join(
            [
                "Analyzing '5d41402abc4b2a76b9719d911017c592'",
                "[+] MD5 [Hashcat Mode: 0] [JtR Format: raw-md5]",
                "[+] MD4 [Hashcat Mode: 900] [JtR Format: raw-md4]",
                "[+] Domain Cached Credentials [Hashcat Mode: 1100]",
            ]
        )
        task = TaskRegistry.create("hashid")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import Tag

        tags = [r for r in results if isinstance(r, Tag)]
        assert len(tags) == 3
        assert tags[0].name == "hash_type"
        assert tags[0].match == "5d41402abc4b2a76b9719d911017c592"
        assert tags[0].category == "crypto"
        assert tags[0].value
        assert tags[1].value
        assert tags[2].value

    def test_hashid_parse_multiple_hashes(self):
        stdout = "\n".join(
            [
                "Analyzing 'abc123'",
                "[+] MD5",
                "Analyzing 'def456'",
                "[+] SHA-1",
            ]
        )
        task = TaskRegistry.create("hashid")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import Tag

        tags = [r for r in results if isinstance(r, Tag)]
        assert len(tags) == 2
        assert tags[0].match == "abc123"
        assert tags[0].value
        assert tags[1].match == "def456"
        assert tags[1].value

    def test_hashid_parse_empty(self):
        task = TaskRegistry.create("hashid")
        assert task.parse_output("", "") == []

class TestJwtToolParser:
    def test_jwt_tool_metadata(self):
        task = TaskRegistry.create("jwt_tool")
        assert task.name == "jwt_tool"
        assert task.cmd == "jwt_tool"
        assert task.category == "vuln/jwt"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_jwt_tool_parse_output(self):
        stdout = "\n".join(
            [
                '[*] sub = "admin"',
                "[*] iat = 1700000000",
                "[+] VULNERABILITY: Algorithm confusion allows forging tokens",
                "[*] Decoded token info line",
                "[+] WEAK key used for signing",
            ]
        )
        task = TaskRegistry.create("jwt_tool")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import Tag

        vulns = [r for r in results if isinstance(r, Vulnerability)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(vulns) == 2
        assert vulns[0].severity == Severity.HIGH
        assert "Algorithm confusion" in vulns[0].name
        claims = [t for t in tags if t.name == "jwt_claim"]
        assert len(claims) == 2
        assert claims[0].value == "sub=admin"
        assert claims[1].value == "iat=1700000000"
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
