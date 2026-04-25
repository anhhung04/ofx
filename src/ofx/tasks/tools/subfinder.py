"""subfinder — fast passive subdomain enumeration."""

from __future__ import annotations

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Subdomain
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("subfinder")
class SubfinderTask(Task):
    name = "subfinder"
    cmd = "subfinder"
    description = "Fast passive subdomain enumeration tool"
    category = "dns/recon"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"
    output_types = [Subdomain]

    opts = {
        "sources": OptDef(flag="-sources", type=str, help="Comma-separated sources"),
        "recursive": OptDef(
            flag="-recursive", is_flag=True, help="Use recursive enumeration"
        ),
        "all": OptDef(flag="-all", is_flag=True, help="Use all sources"),
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "timeout": OptDef(flag="-timeout", type=int, help="Timeout in seconds"),
        "rate_limit": OptDef(
            flag="-rate-limit", type=int, help="Max requests per second"
        ),
        "max_time": OptDef(
            flag="-max-time", type=int, help="Max enumeration time in minutes"
        ),
        "exclude_sources": OptDef(
            flag="-es", type=str, help="Exclude comma-separated sources"
        ),
    }

    input_flag = "-d"
    file_flag = "-dL"
    output_flag = "-o"
    silent_flag = "-silent"

    def _output_suffix(self) -> str:
        return ".txt"

    def parse_line(self, line: str) -> list[Subdomain]:
        host = line.strip()
        if not host or host.startswith("#"):
            return []

        domain = ".".join(host.rsplit(".", 2)[-2:]) if "." in host else host

        return [Subdomain(host=host, domain=domain)]
