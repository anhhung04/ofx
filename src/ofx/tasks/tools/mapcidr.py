"""mapcidr — CIDR expansion and IP manipulation utility."""

from __future__ import annotations

from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Ip
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("mapcidr")
class MapcidrTask(Task):
    name = "mapcidr"
    cmd = "mapcidr"
    description = "CIDR expansion and IP manipulation utility"
    category = "ip/util"
    install_cmd = (
        "GOBIN=~/Tools/bin go install -v"
        " github.com/projectdiscovery/mapcidr/cmd/mapcidr@latest"
    )
    output_types = [Ip]

    opts = {
        "aggregate": OptDef(
            flag="-a", is_flag=True, help="Aggregate IPs/CIDRs"
        ),
        "count": OptDef(
            flag="-count", is_flag=True, help="Count IPs in CIDR"
        ),
        "filter": OptDef(
            flag="-f", type=str, help="Filter IP by port (e.g. 80)"
        ),
    }

    input_flag = "-cidr"
    file_flag = "-cl"
    output_flag = "-o"
    extra_flags = ["-silent"]

    def _output_suffix(self) -> str:
        return ".txt"

    def parse_line(self, line: str) -> list[Ip]:
        line = line.strip()
        if not line or line.startswith("#"):
            return []

        return [Ip(ip=line, alive=False)]

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Ip]:
        results: list[Ip] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results
