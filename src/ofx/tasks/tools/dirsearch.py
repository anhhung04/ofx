"""dirsearch — web path discovery tool with JSON report output."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("dirsearch")
class DirsearchTask(Task):
    name = "dirsearch"
    cmd = "dirsearch"
    description = "Web path scanner / content discovery tool"
    category = "url/fuzz"
    install_cmd = "uv tool install dirsearch"
    output_types = [Url]

    opts = {
        "wordlist": OptDef(flag="-w", type=str, help="Wordlist path"),
        "extensions": OptDef(
            flag="-e", type=str, help="Extensions e.g. php,html,js"
        ),
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "recursive": OptDef(flag="-r", is_flag=True, help="Brute-force recursively"),
        "recursion_depth": OptDef(
            flag="--recursion-depth", type=int, help="Maximum recursion depth"
        ),
        "exclude_status": OptDef(
            flag="--exclude-status",
            type=str,
            help="Exclude status codes e.g. 404,403",
        ),
        "include_status": OptDef(
            flag="--include-status", type=str, help="Include status codes"
        ),
        "method": OptDef(flag="-m", type=str, help="HTTP method"),
        "header": OptDef(flag="-H", type=str, help="Custom header"),
        "cookie": OptDef(flag="--cookie", type=str, help="Cookie string"),
        "proxy": OptDef(flag="--proxy", type=str, help="Proxy URL"),
        "timeout": OptDef(flag="--timeout", type=int, help="Request timeout"),
        "follow_redirects": OptDef(
            flag="--follow-redirects", is_flag=True, help="Follow HTTP redirects"
        ),
        "random_agent": OptDef(
            flag="--random-agent", is_flag=True, help="Use random User-Agent"
        ),
    }

    input_flag = "-u"
    file_flag = "-l"
    output_flag = "-o"
    extra_flags = ["--format", "json", "-q"]

    def _output_suffix(self) -> str:
        return ".json"

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Url]:
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        results: list[Url] = []
        for item in data.get("results", []):
            url = item.get("url", "")
            if not url:
                continue
            results.append(
                Url(
                    url=url,
                    host=urlparse(url).netloc,
                    status_code=self._safe_int(item.get("status", 0)),
                    content_type=item.get("content-type", ""),
                    content_length=self._safe_int(item.get("content-length", 0)),
                    extra_data={"redirect": item.get("redirect", "")},
                )
            )

        return results
