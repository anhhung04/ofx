"""rustscan — ultra-fast port scanner written in Rust."""

from __future__ import annotations

import re
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Port
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("rustscan")
class RustscanTask(Task):
    name = "rustscan"
    cmd = "rustscan"
    description = "Ultra-fast port scanner written in Rust"
    category = "port/scan"
    install_cmd = "cargo install rustscan && mkdir -p ~/Tools/bin && cp ~/.cargo/bin/rustscan ~/Tools/bin/"
    output_types = [Port]

    opts = {
        "ports": OptDef(flag="-p", type=str, help="Ports to scan"),
        "range": OptDef(flag="-r", type=str, help="Port range (1-65535)"),
        "batch_size": OptDef(flag="-b", type=int, help="Batch size"),
        "timeout": OptDef(flag="-t", type=int, help="Timeout in milliseconds"),
        "tries": OptDef(flag="--tries", type=int, help="Number of tries"),
        "ulimit": OptDef(flag="--ulimit", type=int, help="Ulimit value"),
        "scan_order": OptDef(flag="--scan-order", type=str, help="Scan order (serial/random)"),
    }

    input_flag = "-a"
    file_flag = None
    output_flag = None
    extra_flags = ["--greppable", "--accessible"]

    def _output_suffix(self) -> str:
        return ".txt"

    # Open IP:PORT or standalone port lines
    _OPEN_RE = re.compile(r"Open\s+(\S+?):(\d+)", re.IGNORECASE)
    # Greppable grouped: Host: IP () Ports: 22/open/tcp//ssh///, 80/open/tcp//http///
    _GREPPABLE_RE = re.compile(r"Host:\s+(\S+)")
    _PORT_ENTRY_RE = re.compile(r"(\d+)/open/(\w+)//(\w*)")

    def parse_line(self, line: str) -> list[Port]:
        line = line.strip()
        if not line:
            return []
        m = self._OPEN_RE.search(line)
        if m:
            return [
                Port(
                    port=self._safe_int(m.group(2)),
                    ip=m.group(1),
                    state="open",
                    protocol="tcp",
                )
            ]
        return []

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Port]:
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        results: list[Port] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            # Try "Open IP:PORT" lines
            m = self._OPEN_RE.search(line)
            if m:
                results.append(
                    Port(
                        port=self._safe_int(m.group(2)),
                        ip=m.group(1),
                        state="open",
                        protocol="tcp",
                    )
                )
                continue

            # Try greppable format
            host_m = self._GREPPABLE_RE.match(line)
            if host_m:
                ip = host_m.group(1)
                for pm in self._PORT_ENTRY_RE.finditer(line):
                    results.append(
                        Port(
                            port=self._safe_int(pm.group(1)),
                            ip=ip,
                            state="open",
                            protocol=pm.group(2),
                            service_name=pm.group(3),
                        )
                    )

        return results
