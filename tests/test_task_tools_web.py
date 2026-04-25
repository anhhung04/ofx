"""Tests for individual tool parsers, parse_line, streaming detection, and output edge cases."""

import json

from ofx.tasks import (
    Subdomain,
    TaskRegistry,
    Url,
)
from ofx.tasks.output_types import (
    Tag,
)

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
            json.dumps(
                {
                    "target": "https://example.com",
                    "plugins": {
                        "nginx": {"version": ["1.18.0"]},
                        "PHP": {"version": ["7.4"]},
                        "jQuery": {},
                        "Country": {"string": ["US"]},
                    },
                }
            ),
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
        stdout = "\n".join(
            [
                "[200] https://example.com - Example Domain",
                "[301] https://www.example.com - Redirect",
                "[404] https://example.com/missing - Not Found",
            ]
        )
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
        cmd, _ = task.build_command("https://example.com", threads=5, fullpage=True)
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


class TestFeroxbusterParser:
    def test_parse_jsonl(self):
        lines = [
            json.dumps(
                {
                    "type": "response",
                    "url": "https://example.com/admin",
                    "status": 200,
                    "content_length": 5432,
                    "word_count": 120,
                    "line_count": 45,
                    "method": "GET",
                }
            ),
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
        cmd, _ = task.build_command(
            "https://example.com", extensions="php,html", threads=30
        )
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
        assert (
            task.parse_line(
                "==============================================================="
            )
            == []
        )

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
        cmd, out_file = task.build_command(
            "https://example.com/api", method="POST", threads=5
        )
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


class TestKatanaParser:
    def test_parse_jsonl(self):
        lines = [
            json.dumps(
                {
                    "request": {
                        "endpoint": "https://example.com/page",
                        "host": "example.com",
                        "method": "GET",
                    },
                    "response": {"status_code": 200},
                }
            ),
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


# ── Gospider Parser ────────────────────────────────────────────────────


class TestGospiderParser:
    def test_parse_output(self):
        lines = [
            json.dumps(
                {
                    "output": "https://example.com/page",
                    "source": "sitemap",
                    "type": "url",
                }
            ),
            json.dumps(
                {
                    "output": "https://example.com/robots.txt",
                    "source": "robots",
                    "type": "url",
                }
            ),
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
        stdout = "\n".join(
            [
                "https://example.com/",
                "https://example.com/about",
                "https://example.com/contact?ref=home",
            ]
        )
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
            json.dumps(
                {
                    "url": "https://example.com/login",
                    "status_code": 200,
                    "matches": [
                        {"name": "API Key", "match": "AKIA...", "type": "secret"},
                    ],
                }
            ),
            json.dumps(
                {
                    "url": "https://example.com/api",
                    "status_code": 200,
                }
            ),
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
            json.dumps(
                {
                    "url": "https://example.com/page",
                    "secrets": ["AWS_KEY=AKIA12345"],
                }
            ),
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
        result = task.parse_line(
            json.dumps(
                {
                    "url": "https://example.com/test",
                    "status_code": 404,
                }
            )
        )
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
        stdout = "\n".join(
            [
                "[INFO] Fetching URLs...",
                "https://example.com/page?id=FUZZ",
                "https://example.com/search?q=FUZZ&lang=en",
                "/api/v1/data?token=FUZZ",
            ]
        )
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
