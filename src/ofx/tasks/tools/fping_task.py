"""fping — ICMP ping sweep for host discovery."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Ip
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("fping")
class FpingTask(Task):
    name = "fping"
    cmd = "fping"
    description = "ICMP ping sweep for host discovery"
    category = "ip/recon"
    install_cmd = "apt install -y fping"
    output_types = [Ip]

    # fping returns 1 when some hosts are unreachable — normal in network recon.
    success_codes = [0, 1]

    opts = {
        "count": OptDef(flag="-c", type=int, help="Number of pings per target"),
        "timeout": OptDef(flag="-t", type=int, help="Timeout in ms"),
        "retry": OptDef(flag="-r", type=int, help="Number of retries"),
        "generate": OptDef(
            flag="-g", is_flag=True, help="Generate target list from CIDR"
        ),
    }

    input_flag = None  # positional
    file_flag = "-f"
    output_flag = None  # stdout only
    silent_flag = "-q"
    extra_flags = ["-a"]

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Target is positional — appended at the end."""
        parts: list[str] = [self.cmd, *self.extra_flags]
        if self.json_flag:
            parts.append(self.json_flag)
        if self.silent_flag:
            parts.append(self.silent_flag)

        for key, value in kwargs.items():
            if key.startswith("_"):
                continue
            opt = self.opts.get(key)
            if opt is None:
                continue
            if opt.is_flag:
                if value:
                    parts.append(opt.flag)
            elif value is not None:
                parts.extend([opt.flag, str(value)])

        parts.append(target)

        return " ".join(parts), None

    # Match bare IPs or IPs in parentheses
    _IP_RE = re.compile(r"^\(?(\d{1,3}(?:\.\d{1,3}){3})\)?$")

    def parse_line(self, line: str) -> list[Ip]:
        line = line.strip()
        if not line:
            return []

        m = self._IP_RE.match(line)
        if m:
            return [Ip(ip=m.group(1), alive=True)]

        # Also handle plain IPs without regex anchoring issues
        parts = line.split()
        if parts:
            candidate = parts[0].strip("()")
            try:
                octets = candidate.split(".")
                if len(octets) == 4 and all(0 <= int(o) <= 255 for o in octets):
                    return [Ip(ip=candidate, alive=True)]
            except (ValueError, IndexError):
                pass

        return []
