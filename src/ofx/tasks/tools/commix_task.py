"""commix — automated command injection exploitation tool."""

from __future__ import annotations

import re
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Vulnerability
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("commix")
class CommixTask(Task):
    name = "commix"
    cmd = "commix"
    description = "Automated command injection exploitation tool"
    category = "vuln/injection"
    install_cmd = "uv tool install commix"
    output_types = [Vulnerability]

    opts = {
        "data": OptDef(flag="--data", type=str, help="POST data"),
        "cookie": OptDef(flag="--cookie", type=str, help="HTTP cookie"),
        "headers": OptDef(flag="--headers", type=str, help="Custom HTTP headers"),
        "method": OptDef(flag="--method", type=str, help="HTTP method"),
        "level": OptDef(flag="--level", type=int, help="Level of tests (1-3)"),
        "technique": OptDef(
            flag="-t",
            type=str,
            help="Technique (classic,eval-based,time-based,file-based)",
        ),
        "proxy": OptDef(flag="--proxy", type=str, help="Proxy URL"),
        "tor": OptDef(flag="--tor", is_flag=True, help="Use Tor network"),
        "batch": OptDef(flag="--batch", is_flag=True, help="Non-interactive mode"),
        "os": OptDef(flag="--os", type=str, help="Target OS (unix/windows)"),
    }

    input_flag = "-u"
    file_flag = None
    output_flag = None
    extra_flags = ["--batch"]

    def _output_suffix(self) -> str:
        return ".txt"

    _VULN_PARAM_RE = re.compile(r"The parameter '([^']+)' is vulnerable", re.IGNORECASE)
    _TECHNIQUE_RE = re.compile(
        r"The \('([^']+)'\) technique appears to be injectable", re.IGNORECASE
    )

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability]:
        raw = self._raw_output(stdout, output_file)
        if not raw:
            return []

        results: list[Vulnerability] = []
        techniques: list[str] = []

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            m_tech = self._TECHNIQUE_RE.search(line)
            if m_tech:
                techniques.append(m_tech.group(1))
                continue

            m_vuln = self._VULN_PARAM_RE.search(line)
            if m_vuln:
                desc = ""
                if techniques:
                    desc = f"Injectable via: {', '.join(techniques)}"
                results.append(
                    Vulnerability(
                        name="Command Injection",
                        matched_at=m_vuln.group(1),
                        severity=Severity.CRITICAL,
                        provider="commix",
                        description=desc,
                    )
                )
                techniques = []

        return results
