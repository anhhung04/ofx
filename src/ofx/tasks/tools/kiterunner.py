"""kiterunner — API endpoint brute-force discovery."""

from __future__ import annotations

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag, Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("kiterunner")
class KiterunnerTask(Task):
    name = "kiterunner"
    cmd = "kr"
    description = "API endpoint brute-force discovery"
    category = "recon/api"
    install_cmd = (
        "GOBIN=~/Tools/bin go install -v"
        " github.com/assetnote/kiterunner/cmd/kr@latest"
    )
    output_types = [Url, Tag]

    opts = {
        "wordlist": OptDef(flag="-w", type=str, help="Wordlist / kitebuilder schema"),
        "threads": OptDef(flag="-x", type=int, help="Number of concurrent threads"),
        "max_redirects": OptDef(
            flag="--max-redirects", type=int, help="Maximum redirects to follow"
        ),
        "max_connection_per_host": OptDef(
            flag="--max-connection-per-host",
            type=int,
            help="Max connections per host",
        ),
        "delay": OptDef(flag="--delay", type=str, help="Delay between requests"),
        "headers": OptDef(flag="-H", type=str, help="Custom header"),
        "content_type": OptDef(
            flag="--content-type", type=str, help="Content-Type header"
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    subcommand = "scan"
    json_flag = "--json"

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Url | Tag]:
        data = self._parse_json_line(line)
        if data is None:
            return []

        url = data.get("url", "")
        if not url:
            return []

        results: list[Url | Tag] = [
            Url(
                url=url,
                status_code=self._safe_int(data.get("status_code", 0)),
                content_length=self._safe_int(data.get("length", 0)),
            )
        ]

        status = data.get("status_code")
        if status is not None:
            results.append(
                Tag(
                    name="api_endpoint",
                    value=f"{status}",
                    match=url,
                    category="kiterunner",
                )
            )

        return results

