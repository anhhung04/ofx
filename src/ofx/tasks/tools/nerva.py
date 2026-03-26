"""nerva — service detection and fingerprinting tool."""

from __future__ import annotations

import json
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Port, Tag
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("nerva")
class NervaTask(Task):
    name = "nerva"
    cmd = "nerva"
    description = "Service detection and fingerprinting"
    category = "port/fingerprint"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/praetorian-inc/nerva/cmd/nerva@latest"
    output_types = [Port, Tag]

    opts = {
        "workers": OptDef(flag="-W", type=int, help="Number of concurrent scan workers"),
        "timeout": OptDef(flag="-w", type=int, help="Timeout in milliseconds"),
        "rate_limit": OptDef(flag="-R", type=float, help="Max scans per second (0=unlimited)"),
        "max_host_conn": OptDef(flag="-H", type=int, help="Max concurrent connections per host IP"),
        "fast": OptDef(flag="-f", is_flag=True, help="Fast mode"),
        "udp": OptDef(flag="-U", is_flag=True, help="Run UDP plugins"),
        "sctp": OptDef(flag="-S", is_flag=True, help="Run SCTP plugins (Linux only)"),
        "verbose": OptDef(flag="-v", is_flag=True, help="Verbose mode"),
    }

    input_flag = "-t"
    file_flag = "-l"
    output_flag = "-o"
    extra_flags = ["--json"]

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Port | Tag]:
        line = line.strip()
        if not line or not line.startswith("{"):
            return []
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return []

        ip = data.get("ip", data.get("host", ""))
        port_num = self._safe_int(data.get("port", 0))
        if not port_num and not ip:
            return []

        results: list[Port | Tag] = []

        service = data.get("service", data.get("service_name", ""))
        version = data.get("version", "")
        banner = data.get("banner", "")
        product = data.get("product", "")

        service_name = service
        if version:
            service_name = f"{service}/{version}" if service else version

        if port_num:
            results.append(
                Port(
                    port=port_num,
                    ip=ip,
                    host=data.get("host", ip),
                    state="open",
                    protocol=data.get("protocol", "tcp"),
                    service_name=service_name,
                    extra_data={
                        k: v
                        for k, v in {
                            "version": version,
                            "banner": banner,
                            "product": product,
                            "cpe": data.get("cpe", ""),
                        }.items()
                        if v
                    },
                )
            )

        if product:
            results.append(
                Tag(
                    name=product,
                    value=version or product,
                    match=f"{ip}:{port_num}" if port_num else ip,
                    category="service",
                )
            )

        return results

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Port | Tag]:
        results: list[Port | Tag] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results
