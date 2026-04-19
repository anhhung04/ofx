"""arjun — HTTP parameter discovery tool."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag, Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("arjun")
class ArjunTask(Task):
    name = "arjun"
    cmd = "arjun"
    description = "HTTP parameter discovery suite"
    category = "url/fuzz/params"
    install_cmd = "uv tool install arjun"
    output_types = [Url, Tag]

    opts = {
        "method": OptDef(
            flag="-m", type=str, help="HTTP method GET/POST/JSON/XML"
        ),
        "headers": OptDef(flag="--headers", type=str, help="Custom headers"),
        "include": OptDef(
            flag="--include", type=str, help="Include params pattern"
        ),
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "delay": OptDef(flag="-d", type=int, help="Delay between requests"),
        "timeout": OptDef(flag="--timeout", type=int, help="Request timeout"),
        "stable": OptDef(
            flag="--stable", is_flag=True, help="Increase accuracy, reduce speed"
        ),
        "wordlist": OptDef(flag="-w", type=str, help="Custom wordlist"),
    }

    input_flag = "-u"
    file_flag = "-i"
    output_flag = "-oJ"
    silent_flag = "-q"

    def _output_suffix(self) -> str:
        return ".json"

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Url | Tag]:
        data = self._read_json_output(stdout, output_file)
        if data is None:
            return []

        results: list[Url | Tag] = []
        for url_key, item in data.items():
            if not isinstance(item, dict):
                continue
            params = item.get("params", [])
            method = item.get("method", "GET")

            results.append(
                Url(
                    url=url_key,
                    host=urlparse(url_key).netloc,
                    method=method,
                    extra_data={"params": params, "method": method},
                )
            )

            for param in params:
                results.append(
                    Tag(
                        name=param,
                        value="parameter",
                        match=url_key,
                        category="parameter",
                    )
                )

        return results
