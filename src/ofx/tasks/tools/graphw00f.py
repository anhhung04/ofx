"""graphw00f — GraphQL engine fingerprinting tool."""

from __future__ import annotations

import re
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag, Url
from ofx.tasks.registry import TaskRegistry

_ENGINE_RE = re.compile(
    r"(?:is\s+|Detected:\s*)(\w[\w\s.-]*\w)", re.IGNORECASE
)


@TaskRegistry.register("graphw00f")
class Graphw00fTask(Task):
    name = "graphw00f"
    cmd = "graphw00f"
    description = "GraphQL engine fingerprinting tool"
    category = "recon/api"
    install_cmd = "uv tool install graphw00f"
    output_types = [Tag, Url]

    opts = {
        "proxy": OptDef(flag="-p", type=str, help="Proxy URL"),
        "headers": OptDef(flag="-H", type=str, help="Custom header"),
        "burp_file": OptDef(flag="-b", type=str, help="Burp Suite export file"),
    }

    input_flag = "-t"
    file_flag = None
    output_flag = None
    extra_flags = ["-f"]

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Tag | Url]:
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        results: list[Tag | Url] = []
        target: str = ""

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            # Detect target URL echoed in output
            if not target and ("http://" in line or "https://" in line):
                for token in line.split():
                    if token.startswith("http://") or token.startswith("https://"):
                        target = token.rstrip("/.,;")
                        break

            m = _ENGINE_RE.search(line)
            if m:
                engine = m.group(1).strip()
                results.append(
                    Tag(
                        name="graphql_engine",
                        value=engine,
                        match=target or "",
                        category="graphw00f",
                    )
                )

        if target:
            results.append(Url(url=target))

        return results
