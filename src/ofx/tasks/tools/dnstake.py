"""dnstake — DNS takeover detection."""

from __future__ import annotations

import re

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Subdomain, Vulnerability
from ofx.tasks.registry import TaskRegistry

_VULN_RE = re.compile(r"\[VULNERABLE\]\s+(\S+)")


@TaskRegistry.register("dnstake")
class DnstakeTask(Task):
    name = "dnstake"
    cmd = "dnstake"
    description = "DNS takeover detection tool"
    category = "dns/takeover"
    install_cmd = (
        "GOBIN=~/Tools/bin go install -v github.com/pwnesia/dnstake/cmd/dnstake@latest"
    )
    output_types = [Vulnerability, Subdomain]

    opts = {
        "threads": OptDef(flag="-c", type=int, help="Concurrency"),
    }

    input_flag = "-t"
    file_flag = "-l"
    output_flag = "-o"
    silent_flag = "-silent"

    def _output_suffix(self) -> str:
        return ".txt"

    def parse_line(self, line: str) -> list[Vulnerability | Subdomain]:
        line = line.strip()
        if not line:
            return []

        match = _VULN_RE.search(line)
        if match:
            host = match.group(1)
            domain = ".".join(host.rsplit(".", 2)[-2:]) if "." in host else host
            return [
                Vulnerability(
                    name="DNS Takeover",
                    matched_at=host,
                    severity=Severity.HIGH,
                    provider="dnstake",
                    description=line,
                ),
                Subdomain(host=host, domain=domain),
            ]

        # Non-vulnerable lines may still contain a hostname
        parts = line.split()
        for part in parts:
            if "." in part and not part.startswith("["):
                host = part.strip()
                domain = ".".join(host.rsplit(".", 2)[-2:]) if "." in host else host
                return [Subdomain(host=host, domain=domain)]

        return []
