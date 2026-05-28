"""porch-pirate — scan Postman for API leaks and exposed endpoints."""

from __future__ import annotations

import re
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag, Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("porch-pirate")
class PorchPirateTask(Task):
    name = "porch-pirate"
    cmd = "porch-pirate"
    description = "Scan Postman for API leaks and exposed endpoints"
    category = "osint/api"
    install_cmd = "uv tool install porch-pirate"
    output_types = [Url, Tag]

    opts = {
        "globals": OptDef(flag="-g", is_flag=True, help="Search for global variables"),
        "collections": OptDef(flag="-c", is_flag=True, help="Search for collections"),
        "requests": OptDef(flag="-r", is_flag=True, help="Search for requests"),
        "raw": OptDef(flag="--raw", is_flag=True, help="Show raw output"),
    }

    input_flag = "-s"
    file_flag = None
    output_flag = None
    extra_flags = []

    def _output_suffix(self) -> str:
        return ".txt"

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Url | Tag]:
        raw = self._raw_output(stdout, output_file)
        if not raw:
            return []

        results: list[Url | Tag] = []
        seen_urls: set[str] = set()

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            # Extract URLs
            for url_match in re.finditer(r"(https?://\S+)", line):
                url = url_match.group(1).rstrip(".,;\"')")
                if url not in seen_urls:
                    seen_urls.add(url)
                    results.append(Url(url=url))

            # Tag lines containing potential secrets
            secret_patterns = [
                (r"(?:api[_-]?key|apikey)\s*[:=]\s*(\S+)", "api-key"),
                (r"(?:token|bearer)\s*[:=]\s*(\S+)", "token"),
                (r"(?:password|passwd|pwd)\s*[:=]\s*(\S+)", "password"),
                (r"(?:secret|client_secret)\s*[:=]\s*(\S+)", "secret"),
                (r"(?:auth|authorization)\s*[:=]\s*(\S+)", "auth"),
            ]
            for pattern, category in secret_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    results.append(
                        Tag(
                            name=category,
                            value=match.group(1)[:50],
                            match=line[:200],
                            category="postman-leak",
                        )
                    )

            # Tag workspace/collection names
            if line.startswith("Collection:") or line.startswith("Workspace:"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    results.append(
                        Tag(
                            name=parts[0].strip().lower(),
                            value=parts[1].strip(),
                            match=line,
                            category="postman",
                        )
                    )

        return results
