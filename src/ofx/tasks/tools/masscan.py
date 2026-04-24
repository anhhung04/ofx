"""masscan — ultra-fast internet port scanner."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Ip, Port
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("masscan")
class MasscanTask(Task):
    name = "masscan"
    cmd = "masscan"
    description = "Ultra-fast internet port scanner"
    category = "port/scan"
    install_cmd = "apt install -y masscan"
    output_types = [Port, Ip]

    opts = {
        "ports": OptDef(flag="-p", type=str, help="Port range to scan"),
        "rate": OptDef(flag="--rate", type=int, help="Packets per second"),
        "top_ports": OptDef(
            flag="--top-ports", type=str, help="Scan top N ports"
        ),
        "banners": OptDef(
            flag="--banners", is_flag=True, help="Grab banners from services"
        ),
        "interface": OptDef(flag="-e", type=str, help="Network interface to use"),
        "source_ip": OptDef(
            flag="--adapter-ip", type=str, help="Source IP address"
        ),
        "exclude": OptDef(flag="--exclude", type=str, help="Exclude hosts"),
        "wait": OptDef(
            flag="--wait", type=int, help="Seconds to wait after transmit done"
        ),
    }

    input_flag = None  # positional
    file_flag = "-iL"
    output_flag = "-oJ"
    extra_flags = ["--rate=1000"]

    def _output_suffix(self) -> str:
        return ".json"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Target is positional; override default rate if ``rate`` kwarg is set."""
        parts: list[str] = [self.cmd]

        # Only include the default --rate flag if the user didn't override it
        rate_override = kwargs.get("rate")
        if rate_override is not None:
            parts.append(f"--rate={rate_override}")
        else:
            parts.extend(self.extra_flags)

        for key, value in kwargs.items():
            if key.startswith("_") or key == "rate":
                continue
            opt = self.opts.get(key)
            if opt is None:
                continue
            if opt.is_flag:
                if value:
                    parts.append(opt.flag)
            elif value is not None:
                parts.extend([opt.flag, str(value)])

        output_file: Path | None = None
        if self.output_flag:
            # Generate a unique path without pre-creating the file — masscan
            # (which may run as root) must create the output file itself.
            # Pre-creating with mkstemp can cause "could not open file for
            # writing" when masscan runs as a different uid (e.g. via sudo).
            _fd, _path = tempfile.mkstemp(
                prefix=f".ofx_task_{self.name}_",
                suffix=self._output_suffix(),
            )
            os.close(_fd)
            os.unlink(_path)
            output_file = Path(_path)
            parts.extend([self.output_flag, str(output_file)])

        # masscan only accepts IPs/CIDRs — resolve hostnames automatically
        resolved = self._resolve_to_ip(target)
        parts.append(resolved)

        return " ".join(parts), output_file

    @staticmethod
    def _resolve_to_ip(target: str) -> str:
        """Resolve a hostname to IP if needed — masscan only accepts IPs/CIDRs."""
        import socket

        target = target.strip()

        # Already an IP or CIDR — pass through
        base = target.split("/")[0]
        try:
            socket.inet_pton(socket.AF_INET, base)
            return target
        except OSError:
            pass

        # File path — pass through
        if Path(target).is_file():
            return target

        # Hostname — resolve
        try:
            info = socket.getaddrinfo(base, None, socket.AF_INET, socket.SOCK_STREAM)
            if info:
                return str(info[0][4][0])
        except socket.gaierror:
            pass

        return target

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Port | Ip]:
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        # masscan JSON output may have trailing commas or be wrapped in []
        # Strip the trailing comma before the closing bracket if present
        raw = raw.rstrip().rstrip(",")
        if not raw.startswith("["):
            raw = f"[{raw}]"

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        results: list[Port | Ip] = []
        seen_ips: set[str] = set()

        for entry in data:
            ip = entry.get("ip", "")
            if not ip:
                continue

            if ip not in seen_ips:
                seen_ips.add(ip)
                results.append(Ip(ip=ip, alive=True))

            for port_info in entry.get("ports", []):
                portnum = self._safe_int(port_info.get("port", 0))
                if not portnum:
                    continue
                results.append(
                    Port(
                        port=portnum,
                        ip=ip,
                        state=port_info.get("status", "open"),
                        protocol=port_info.get("proto", "tcp"),
                        service_name=port_info.get("service", {}).get("name", "")
                        if isinstance(port_info.get("service"), dict)
                        else "",
                        extra_data={
                            k: v
                            for k, v in port_info.items()
                            if k not in ("port", "proto", "status", "service")
                        },
                    )
                )

        return results
