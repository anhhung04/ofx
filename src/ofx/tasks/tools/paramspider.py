"""paramspider — URL parameter mining from web archives."""

from __future__ import annotations

from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("paramspider")
class ParamspiderTask(Task):
    name = "paramspider"
    cmd = "paramspider"
    description = "URL parameter mining from web archives"
    category = "url/recon/params"
    install_cmd = "uv tool install paramspider"
    output_types = [Url]

    opts = {
        "exclude": OptDef(flag="--exclude", type=str, help="Comma-separated extensions to exclude"),
        "subs": OptDef(flag="-s", is_flag=True, help="Include subdomains"),
        "level": OptDef(flag="--level", type=str, help="URL path level"),
    }

    input_flag = "-d"
    file_flag = "-l"
    output_flag = None
    extra_flags = ["--stream"]

    def _output_suffix(self) -> str:
        return ".txt"

    def parse_line(self, line: str) -> list[Url]:
        line = line.strip()
        if not line or line.startswith("["):
            return []
        if "://" in line or line.startswith("/"):
            return [Url(url=line)]
        return []

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
