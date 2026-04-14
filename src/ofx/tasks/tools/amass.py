"""amass — OWASP subdomain enumeration engine."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Subdomain
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("amass")
class AmassTask(Task):
    name = "amass"
    cmd = "amass"
    description = "OWASP subdomain enumeration engine"
    category = "dns/recon"
    install_cmd = (
        "GOBIN=~/Tools/bin go install -v github.com/owasp-amass/amass/v3/...@master"
    )
    output_types = [Subdomain]

    opts = {
        "active": OptDef(
            flag="-active", is_flag=True, help="Enable active recon methods"
        ),
        "brute": OptDef(
            flag="-brute", is_flag=True, help="Enable brute force subdomain guessing"
        ),
        "timeout": OptDef(flag="-timeout", type=int, help="Timeout in minutes"),
        "sources": OptDef(flag="-src", type=str, help="Data source filter"),
        "max_dns_queries": OptDef(
            flag="-max-dns-queries", type=int, help="Maximum concurrent DNS queries"
        ),
    }

    input_flag = "-d"
    file_flag = "-df"
    output_flag = "-o"
    silent_flag = "-silent"
    extra_flags = ["-passive"]

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Prepend ``enum`` subcommand before flags and target."""
        parts: list[str] = [self.cmd, "enum"]

        # If active mode is requested, don't include -passive
        active = kwargs.get("active", False)
        if active:
            parts.append("-active")
        else:
            parts.extend(self.extra_flags)

        if self.json_flag:
            parts.append(self.json_flag)
        if self.silent_flag:
            parts.append(self.silent_flag)

        for key, value in kwargs.items():
            if key.startswith("_") or key == "active":
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
            _fd, _path = tempfile.mkstemp(
                prefix=f".ofx_task_{self.name}_",
                suffix=self._output_suffix(),
            )
            os.close(_fd)
            output_file = Path(_path)
            parts.extend([self.output_flag, str(output_file)])

        parts.extend([self.input_flag, target])

        return " ".join(parts), output_file

    def parse_line(self, line: str) -> list[Subdomain]:
        host = line.strip()
        if not host or host.startswith("#"):
            return []

        domain = ".".join(host.rsplit(".", 2)[-2:]) if "." in host else host

        return [Subdomain(host=host, domain=domain)]

