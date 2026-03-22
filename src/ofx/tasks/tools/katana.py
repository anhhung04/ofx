"""katana — next-gen crawling and spidering framework."""

from __future__ import annotations

import json
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("katana")
class KatanaTask(Task):
    name = "katana"
    cmd = "katana"
    description = "Next-generation crawling and spidering framework"
    category = "url/crawl"
    install_cmd = "GOBIN=~/Tools/bin go install github.com/projectdiscovery/katana/cmd/katana@latest"
    output_types = [Url]

    opts = {
        "depth": OptDef(flag="-depth", type=int, help="Maximum depth to crawl"),
        "js_crawl": OptDef(
            flag="-js-crawl", is_flag=True, help="Enable JS file crawling"
        ),
        "headless": OptDef(flag="-headless", is_flag=True, help="Use headless browser"),
        "scope": OptDef(flag="-crawl-scope", type=str, help="Regex for crawl scope"),
        "out_scope": OptDef(
            flag="-crawl-out-scope", type=str, help="Regex for out of scope"
        ),
        "known_files": OptDef(
            flag="-known-files",
            type=str,
            help="Enable crawling of known files (all, robotstxt, sitemapxml)",
        ),
        "automatic_form_fill": OptDef(
            flag="-automatic-form-fill", is_flag=True, help="Fill forms automatically"
        ),
        "rate_limit": OptDef(
            flag="-rate-limit", type=int, help="Max requests per second"
        ),
        "concurrency": OptDef(
            flag="-concurrency", type=int, help="Number of concurrent fetchers"
        ),
        "parallelism": OptDef(
            flag="-parallelism", type=int, help="Number of concurrent inputs"
        ),
        "timeout": OptDef(flag="-timeout", type=int, help="Request timeout in seconds"),
        "delay": OptDef(flag="-delay", type=int, help="Delay between requests"),
        "strategy": OptDef(
            flag="-strategy",
            type=str,
            help="Crawling strategy (depth-first, breadth-first)",
        ),
        "extensions": OptDef(
            flag="-extension-filter", type=str, help="Extension filter (e.g. png,jpg)"
        ),
        "match_regex": OptDef(
            flag="-match-regex", type=str, help="Match output URL regex"
        ),
        "filter_regex": OptDef(
            flag="-filter-regex", type=str, help="Filter output URL regex"
        ),
    }

    input_flag = "-u"
    file_flag = "-list"
    output_flag = "-o"
    extra_flags = ["-jsonl", "-silent"]

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Url]:
        line = line.strip()
        if not line:
            return []

        # Try JSON first (katana -jsonl output)
        if line.startswith("{"):
            try:
                data = json.loads(line)
                url = data.get("request", {}).get("endpoint", data.get("url", ""))
                if not url:
                    return []
                return [
                    Url(
                        url=url,
                        host=data.get("request", {}).get("host", ""),
                        status_code=self._safe_int(
                            data.get("response", {}).get("status_code", 0)
                        ),
                        method=data.get("request", {}).get("method", "GET"),
                    )
                ]
            except json.JSONDecodeError:
                return []
        else:
            # Plain URL line
            if line.startswith("http://") or line.startswith("https://"):
                return [Url(url=line)]

        return []

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Url]:
        results: list[Url] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results
