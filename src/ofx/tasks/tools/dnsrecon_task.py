"""dnsrecon — DNS enumeration and reconnaissance tool."""

from __future__ import annotations

import json
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Record, Subdomain
from ofx.tasks.registry import TaskRegistry

_ADDRESS_TYPES = {"A", "AAAA"}


@TaskRegistry.register("dnsrecon")
class DnsreconTask(Task):
    name = "dnsrecon"
    cmd = "dnsrecon"
    description = "DNS enumeration and reconnaissance tool"
    category = "dns/recon"
    install_cmd = "uv tool install dnsrecon"
    output_types = [Record, Subdomain]

    opts = {
        "type": OptDef(
            flag="-t",
            type=str,
            help="Enumeration type: std,brt,rvl,srv,axfr,snoop,zonewalk",
        ),
        "threads": OptDef(flag="--threads", type=int, help="Number of threads"),
        "lifetime": OptDef(
            flag="--lifetime", type=int, help="DNS query timeout"
        ),
        "nameserver": OptDef(
            flag="-n", type=str, help="Domain server to use"
        ),
        "wordlist": OptDef(
            flag="-D", type=str, help="Wordlist for brute force"
        ),
        "range": OptDef(
            flag="-r", type=str, help="IP range for reverse lookup"
        ),
    }

    input_flag = "-d"
    file_flag = None
    output_flag = "-j"
    extra_flags = []

    def _output_suffix(self) -> str:
        return ".json"

    @staticmethod
    def _base_domain(name: str) -> str:
        """Extract base domain from a FQDN."""
        name = name.rstrip(".")
        parts = name.rsplit(".", 2)
        return ".".join(parts[-2:]) if len(parts) >= 2 else name

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Record | Subdomain]:
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        if not isinstance(data, list):
            return []

        results: list[Record | Subdomain] = []

        for entry in data:
            if not isinstance(entry, dict):
                continue

            rec_type = entry.get("type", "")
            name = entry.get("name", "")
            address = entry.get("address", "")

            if not name and not rec_type:
                continue

            results.append(
                Record(
                    name=name,
                    type=rec_type,
                    host=address,
                    extra_data=entry,
                )
            )

            if rec_type in _ADDRESS_TYPES and name:
                results.append(
                    Subdomain(
                        host=name.rstrip("."),
                        domain=self._base_domain(name),
                    )
                )

        return results
