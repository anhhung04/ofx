"""maigret — OSINT username checker across social networks."""

from __future__ import annotations

import json
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("maigret")
class MaigretTask(Task):
    name = "maigret"
    cmd = "maigret"
    description = "Collect user account information from social networks"
    category = "user/recon"
    install_cmd = "uv tool install maigret"
    output_types = [UserAccount]

    opts = {
        "timeout": OptDef(flag="--timeout", type=int, help="Request timeout in seconds"),
        "retries": OptDef(flag="-r", type=int, help="Number of retries"),
        "top_sites": OptDef(
            flag="--top-sites", type=int, help="Check only top N popular sites"
        ),
        "all_sites": OptDef(flag="-a", is_flag=True, help="Check all available sites"),
        "tor": OptDef(flag="--tor", is_flag=True, help="Route traffic through Tor"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["--json", "ndjson"]

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[UserAccount]:
        line = line.strip()
        if not line or not line.startswith("{"):
            return []
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return []

        site_name = data.get("siteName", data.get("site_name", ""))
        url_user = data.get("url", data.get("url_user", ""))
        username = data.get("username", "")

        if not site_name and not url_user:
            return []

        if not username:
            return []

        return [
            UserAccount(
                username=username,
                source=site_name,
                extra_data={"url": url_user, "site": site_name},
            )
        ]

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[UserAccount]:
        results: list[UserAccount] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results
