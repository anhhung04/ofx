"""favirecon — favicon hash technology detection."""

from __future__ import annotations

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag, Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("favirecon")
class FavireconTask(Task):
    name = "favirecon"
    cmd = "favirecon"
    description = "Favicon hash technology detection"
    category = "web/recon"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/edoardottt/favirecon/cmd/favirecon@latest"
    output_types = [Tag, Url]

    opts = {
        "threads": OptDef(flag="-c", type=int, help="Concurrency"),
        "timeout": OptDef(flag="-timeout", type=int, help="Timeout in seconds"),
        "rate_limit": OptDef(flag="-rl", type=int, help="Rate limit per second"),
    }

    input_flag = "-u"
    file_flag = "-l"
    output_flag = "-o"
    json_flag = "-json"
    silent_flag = "-silent"

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Tag | Url]:
        data = self._parse_json_line(line)
        if data is None:
            return []

        url = data.get("url", "")
        technology = data.get("technology", "")
        hash_val = str(data.get("hash", ""))

        results: list[Tag | Url] = []

        if technology:
            results.append(
                Tag(
                    name=technology,
                    value=hash_val,
                    match=url,
                    category="favicon",
                )
            )

        if url:
            results.append(Url(url=url))

        return results
