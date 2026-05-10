"""naabu — fast port scanner written in Go."""

from __future__ import annotations

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Port
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("naabu")
class NaabuTask(Task):
    name = "naabu"
    cmd = "naabu"
    description = "Fast port scanner written in Go"
    category = "port/scan"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@latest"
    output_types = [Port]

    opts = {
        "ports": OptDef(flag="-p", type=str, help="Ports to scan (e.g. 80,443,1-1000)"),
        "top_ports": OptDef(
            flag="-top-ports", type=str, help="Top ports (full, 100, 1000)"
        ),
        "scan_type": OptDef(
            flag="-scan-type", type=str, help="Scan type (SYN/CONNECT)"
        ),
        "rate": OptDef(flag="-rate", type=int, help="Packets per second"),
        "retries": OptDef(flag="-retries", type=int, help="Number of retries"),
        "timeout": OptDef(flag="-timeout", type=int, help="Timeout in milliseconds"),
        "threads": OptDef(flag="-c", type=int, help="General concurrency"),
        "warm_up_time": OptDef(
            flag="-warm-up-time", type=int, help="Warm up time between batch of packets"
        ),
        "exclude_ports": OptDef(
            flag="-exclude-ports", type=str, help="Ports to exclude"
        ),
        "nmap": OptDef(flag="-nmap", is_flag=True, help="Run nmap on found ports"),
        "nmap_cli": OptDef(
            flag="-nmap-cli", type=str, help="Nmap CLI arguments to run"
        ),
        "interface": OptDef(
            flag="-interface", type=str, help="Network interface to use"
        ),
        "source_ip": OptDef(flag="-source-ip", type=str, help="Source IP to use"),
    }

    input_flag = "-host"
    file_flag = "-list"
    output_flag = "-o"
    json_flag = "-json"
    silent_flag = "-silent"

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Port]:
        data = self._parse_json_line(line)
        if data is None:
            return []

        ip = data.get("ip", data.get("host", ""))
        port = self._safe_int(data.get("port", 0))
        if not port:
            return []

        return [
            Port(
                port=port,
                ip=ip,
                host=data.get("host", ip),
                state="open",
                protocol=data.get("protocol", "tcp"),
                service_name="",
            )
        ]
