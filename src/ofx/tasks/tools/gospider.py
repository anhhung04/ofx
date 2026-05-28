"""gospider — fast web spider for link and endpoint discovery."""

from __future__ import annotations

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("gospider")
class GospiderTask(Task):
    name = "gospider"
    cmd = "gospider"
    description = "Fast web spider written in Go"
    category = "url/crawl"
    install_cmd = (
        "GOBIN=$TOOLS_BIN_DIR go install -v github.com/jaeles-project/gospider@latest"
    )
    output_types = [Url]

    opts = {
        "depth": OptDef(flag="-d", type=int, help="Maximum depth to crawl"),
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "concurrent": OptDef(flag="-c", type=int, help="Concurrent requests per site"),
        "timeout": OptDef(
            flag="--timeout", type=int, help="Request timeout in seconds"
        ),
        "include_subs": OptDef(
            flag="--include-subs", is_flag=True, help="Include subdomains"
        ),
        "include_other": OptDef(
            flag="--include-other-source",
            is_flag=True,
            help="Include other sources (robots.txt, sitemap, etc.)",
        ),
    }

    input_flag = "-s"
    file_flag = "-S"
    output_flag = None
    json_flag = "--json"
    silent_flag = "-q"

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Url]:
        data = self._parse_json_line(line)
        if data is None:
            return []

        url = data.get("output", "")
        if not url:
            return []

        return [Url(url=url, host=self._url_host(url))]
