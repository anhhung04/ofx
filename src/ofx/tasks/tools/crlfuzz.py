"""crlfuzz — CRLF injection vulnerability scanner."""

from __future__ import annotations

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Vulnerability
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("crlfuzz")
class CrlfuzzTask(Task):
    name = "crlfuzz"
    cmd = "crlfuzz"
    description = "CRLF injection vulnerability scanner"
    category = "vuln/injection"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/dwisiswant0/crlfuzz/cmd/crlfuzz@latest"
    output_types = [Vulnerability]

    opts = {
        "method": OptDef(flag="-X", type=str, help="HTTP method"),
        "headers": OptDef(flag="-H", type=str, help="Custom headers"),
        "data": OptDef(flag="-d", type=str, help="POST data"),
        "concurrency": OptDef(flag="-c", type=int, help="Number of concurrent workers"),
        "proxy": OptDef(flag="-x", type=str, help="Proxy URL"),
    }

    input_flag = "-u"
    file_flag = "-l"
    output_flag = "-o"
    silent_flag = "-s"

    def _output_suffix(self) -> str:
        return ".txt"

    def parse_line(self, line: str) -> list[Vulnerability]:
        line = line.strip()
        if not line or line.startswith("["):
            return []
        if "://" in line:
            return [
                Vulnerability(
                    name="CRLF Injection",
                    matched_at=line,
                    severity=Severity.MEDIUM,
                    provider="crlfuzz",
                )
            ]
        return []
