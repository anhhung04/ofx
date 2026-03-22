"""httpx — fast HTTP prober and technology detector."""

from __future__ import annotations

import json
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag, Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("httpx")
class HttpxTask(Task):
    name = "httpx"
    cmd = "httpx"
    description = "Fast and multi-purpose HTTP toolkit"
    category = "url/probe"
    install_cmd = "go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest"
    output_types = [Url, Tag]

    opts = {
        "tech_detect": OptDef(
            flag="-tech-detect", is_flag=True, help="Detect technologies"
        ),
        "status_code": OptDef(
            flag="-status-code", is_flag=True, help="Show status code"
        ),
        "title": OptDef(flag="-title", is_flag=True, help="Show page title"),
        "web_server": OptDef(flag="-web-server", is_flag=True, help="Show web server"),
        "content_type": OptDef(
            flag="-content-type", is_flag=True, help="Show content type"
        ),
        "follow_redirects": OptDef(
            flag="-follow-redirects", is_flag=True, help="Follow redirects"
        ),
        "threads": OptDef(flag="-threads", type=int, help="Number of threads"),
        "rate_limit": OptDef(
            flag="-rate-limit", type=int, help="Max requests per second"
        ),
        "timeout": OptDef(flag="-timeout", type=int, help="Timeout in seconds"),
        "retries": OptDef(flag="-retries", type=int, help="Number of retries"),
        "match_code": OptDef(flag="-mc", type=str, help="Match status codes"),
        "filter_code": OptDef(flag="-fc", type=str, help="Filter status codes"),
        "ports": OptDef(flag="-ports", type=str, help="Ports to probe"),
    }

    input_flag = "-u"
    file_flag = "-l"
    output_flag = "-o"
    extra_flags = ["-json", "-silent"]

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Url | Tag]:
        line = line.strip()
        if not line or not line.startswith("{"):
            return []
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return []

        url = data.get("url", data.get("input", ""))
        if not url:
            return []

        tech = data.get("tech", [])
        if isinstance(tech, str):
            tech = [tech]

        results: list[Url | Tag] = [
            Url(
                url=url,
                host=data.get("host", ""),
                status_code=self._safe_int(
                    data.get("status_code", data.get("status-code", 0))
                ),
                title=data.get("title", ""),
                content_type=data.get("content_type", data.get("content-type", "")),
                content_length=self._safe_int(
                    data.get("content_length", data.get("content-length", 0))
                ),
                tech=tech,
                webserver=data.get("webserver", ""),
                method=data.get("method", ""),
                words=self._safe_int(data.get("words", 0)),
                lines=self._safe_int(data.get("lines", 0)),
            )
        ]

        for t in tech:
            results.append(Tag(name=t, value=t, match=url, category="technology"))

        return results

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Url | Tag]:
        results: list[Url | Tag] = []
        lines = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results
