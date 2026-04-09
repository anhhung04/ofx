"""asnmap — ASN to CIDR mapping."""

from __future__ import annotations

import json

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Ip
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("asnmap")
class AsnmapTask(Task):
    name = "asnmap"
    cmd = "asnmap"
    description = "ASN to CIDR mapping tool"
    category = "recon/asn"
    install_cmd = (
        "GOBIN=~/Tools/bin go install -v github.com/projectdiscovery/asnmap/cmd/asnmap@latest"
    )
    output_types = [Ip]

    opts = {
        "asn": OptDef(flag="-a", type=str, help="ASN number (e.g. AS1234)"),
        "ip": OptDef(flag="-i", type=str, help="IP address to look up"),
        "resolvers": OptDef(flag="-r", type=str, help="Resolver file path"),
    }

    input_flag = "-d"
    file_flag = "-df"
    output_flag = "-o"
    json_flag = "-json"
    silent_flag = "-silent"

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Ip]:
        line = line.strip()
        if not line or not line.startswith("{"):
            return []
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return []

        as_range = data.get("as_range", "")
        if not as_range:
            return []

        return [
            Ip(
                ip=as_range,
                host=data.get("input", ""),
                extra_data={
                    k: v
                    for k, v in {
                        "as_number": data.get("as_number"),
                        "as_name": data.get("as_name"),
                        "as_country": data.get("as_country"),
                    }.items()
                    if v
                },
            )
        ]

