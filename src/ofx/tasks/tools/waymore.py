"""waymore — comprehensive passive URL collection from web archives."""

from __future__ import annotations

from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("waymore")
class WaymoreTask(Task):
    name = "waymore"
    cmd = "waymore"
    description = "Comprehensive passive URL collection from web archives"
    category = "url/passive"
    install_cmd = "uv tool install waymore"
    output_types = [Url]

    opts = {
        "mode": OptDef(flag="-mode", type=str, help="Mode: U (URLs), R (responses), B (both)"),
        "timeout": OptDef(flag="-t", type=int, help="Timeout in minutes"),
        "limit": OptDef(flag="-l", type=int, help="URL limit"),
        "threads": OptDef(flag="-p", type=int, help="Number of processes"),
    }

    input_flag = "-i"
    file_flag = None
    output_flag = "-oU"
    extra_flags = ["-mode", "U"]

    def _output_suffix(self) -> str:
        return ".txt"

    def parse_line(self, line: str) -> list[Url]:
        url = line.strip()
        if not url or url.startswith("#"):
            return []
        return [Url(url=url)]

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Url]:
        results: list[Url] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results
