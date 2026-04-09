"""csprecon — CSP header subdomain discovery."""

from __future__ import annotations

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Subdomain
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("csprecon")
class CspreconTask(Task):
    name = "csprecon"
    cmd = "csprecon"
    description = "CSP header subdomain discovery"
    category = "dns/recon"
    install_cmd = (
        "GOBIN=~/Tools/bin go install -v github.com/edoardottt/csprecon/cmd/csprecon@latest"
    )
    output_types = [Subdomain]

    opts = {
        "domain": OptDef(flag="-d", type=str, help="Filter by root domain"),
        "threads": OptDef(flag="-c", type=int, help="Concurrency"),
    }

    input_flag = "-u"
    file_flag = "-l"
    output_flag = "-o"

    def _output_suffix(self) -> str:
        return ".txt"

    def parse_line(self, line: str) -> list[Subdomain]:
        host = line.strip()
        if not host or host.startswith("#"):
            return []

        domain = ".".join(host.rsplit(".", 2)[-2:]) if "." in host else host
        return [Subdomain(host=host, domain=domain)]

