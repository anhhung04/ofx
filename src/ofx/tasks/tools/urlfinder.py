"""urlfinder — passive URL extraction from web archives and sources."""

from __future__ import annotations

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("urlfinder")
class UrlfinderTask(Task):
    name = "urlfinder"
    cmd = "urlfinder"
    description = "Passive URL extraction from web archives and sources"
    category = "web/recon"
    install_cmd = "GOBIN=$TOOLS_BIN_DIR go install -v github.com/projectdiscovery/urlfinder/cmd/urlfinder@latest"
    output_types = [Url]

    opts = {
        "all": OptDef(flag="-all", is_flag=True, help="Use all sources"),
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "timeout": OptDef(flag="-timeout", type=int, help="Timeout in seconds"),
        "max_time": OptDef(
            flag="-max-time", type=int, help="Max enumeration time in minutes"
        ),
        "sources": OptDef(
            flag="-sources", type=str, help="Comma-separated sources to use"
        ),
        "exclude_sources": OptDef(
            flag="-es", type=str, help="Exclude comma-separated sources"
        ),
        "filter": OptDef(flag="-f", type=str, help="Filter output using regex"),
        "match": OptDef(flag="-m", type=str, help="Match output using regex"),
    }

    input_flag = "-d"
    file_flag = "-dL"
    output_flag = "-o"
    silent_flag = "-silent"

    def _output_suffix(self) -> str:
        return ".txt"

    def parse_line(self, line: str) -> list[Url]:
        url = line.strip()
        if not url:
            return []

        if url.startswith("http://") or url.startswith("https://"):
            return [Url(url=url)]

        return []
