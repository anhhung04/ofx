"""x8 — hidden parameter discovery tool."""

from __future__ import annotations

import json
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("x8")
class X8Task(Task):
    name = "x8"
    cmd = "x8"
    description = "Hidden parameter discovery tool"
    category = "url/fuzz/params"
    install_cmd = (
        "cargo install x8 && mkdir -p ~/Tools/bin"
        " && cp ~/.cargo/bin/x8 ~/Tools/bin/"
    )
    output_types = [Tag]

    opts = {
        "wordlist": OptDef(flag="-w", type=str, help="Wordlist file"),
        "method": OptDef(flag="-X", type=str, help="HTTP method"),
        "headers": OptDef(flag="-H", type=str, help="Custom header"),
        "data": OptDef(flag="-b", type=str, help="Body for POST requests"),
        "threads": OptDef(flag="-c", type=int, help="Concurrency level"),
        "timeout": OptDef(flag="--timeout", type=int, help="Request timeout"),
        "rate": OptDef(flag="--rate", type=int, help="Requests per second"),
        "param_template": OptDef(
            flag="--param-template", type=str, help="Parameter template"
        ),
        "proxy": OptDef(flag="-x", type=str, help="HTTP proxy"),
        "remove": OptDef(
            flag="--remove",
            type=str,
            help="Remove parameter from output",
        ),
    }

    input_flag = "-u"
    file_flag = None
    output_flag = "-o"
    extra_flags = ["--json"]

    def _output_suffix(self) -> str:
        return ".json"

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Tag]:
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

        results: list[Tag] = []

        entries = data if isinstance(data, list) else [data]

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            url = entry.get("url", "")
            method = entry.get("method", "")
            params = entry.get("parameters", [])

            if not isinstance(params, list):
                continue

            for param in params:
                results.append(
                    Tag(
                        name="hidden_param",
                        value=str(param),
                        match=url,
                        category="param",
                        extra_data={"method": method},
                    )
                )

        return results
