"""subzy — subdomain takeover vulnerability checker."""

from __future__ import annotations

import re

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Vulnerability
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("subzy")
class SubzyTask(Task):
    name = "subzy"
    cmd = "subzy"
    description = "Subdomain takeover vulnerability checker"
    category = "vuln/takeover"
    install_cmd = "GOBIN=$TOOLS_BIN_DIR go install -v github.com/PentestPad/subzy@latest"
    output_types = [Vulnerability]

    opts = {
        "concurrency": OptDef(
            flag="--concurrency", type=int, help="Number of concurrent checks"
        ),
        "timeout": OptDef(flag="--timeout", type=int, help="Timeout in seconds"),
        "https": OptDef(flag="--https", is_flag=True, help="Use HTTPS"),
    }

    input_flag = "--target"
    file_flag = "--targets"
    output_flag = None
    extra_flags = ["run", "--hide_fails", "--vuln"]

    def _output_suffix(self) -> str:
        return ".txt"

    # [VULNERABLE] subdomain.example.com - Service: GitHub Pages - ...
    _VULN_RE = re.compile(
        r"\[VULNERABLE\]\s+(\S+)\s*-\s*(?:Service:\s*)?(.+)", re.IGNORECASE
    )

    def parse_line(self, line: str) -> list[Vulnerability]:
        line = line.strip()
        if not line:
            return []
        m = self._VULN_RE.search(line)
        if m:
            return [
                Vulnerability(
                    name="Subdomain Takeover",
                    matched_at=m.group(1),
                    severity=Severity.HIGH,
                    provider="subzy",
                    description=m.group(2).strip(),
                )
            ]
        return []
