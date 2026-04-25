"""nerva — service detection and fingerprinting tool."""

from __future__ import annotations

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
        "workers": OptDef(
            flag="-W", type=int, help="Number of concurrent scan workers"
        ),
        "timeout": OptDef(flag="-w", type=int, help="Timeout in milliseconds"),
        "rate_limit": OptDef(
            flag="-R", type=float, help="Max scans per second (0=unlimited)"
        ),
        "max_host_conn": OptDef(
            flag="-H", type=int, help="Max concurrent connections per host IP"
        ),
        "fast": OptDef(flag="-f", is_flag=True, help="Fast mode"),
        "udp": OptDef(flag="-U", is_flag=True, help="Run UDP plugins"),
        "sctp": OptDef(flag="-S", is_flag=True, help="Run SCTP plugins (Linux only)"),
        "verbose": OptDef(flag="-v", is_flag=True, help="Verbose mode"),
    }

    input_flag = "-t"
    file_flag = "-l"
    output_flag = "-o"
    json_flag = "--json"

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Port | Tag]:
        data = self._parse_json_line(line)
        if data is None:
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
