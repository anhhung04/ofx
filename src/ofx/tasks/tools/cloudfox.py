"""cloudfox — AWS/Azure/GCP enumeration tool."""

from __future__ import annotations

import re
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry

# Matches table rows with a leading pipe character (cloudfox tabular output)
_TABLE_ROW_RE = re.compile(r"^\s*\|\s*(.+?)\s*\|\s*$")
_FINDING_RE = re.compile(
    r"(?:FINDING|WARNING|ALERT|CRITICAL|HIGH|MEDIUM|LOW)[\s:]+(.+)",
    re.IGNORECASE,
)


@TaskRegistry.register("cloudfox")
class CloudfoxTask(Task):
    name = "cloudfox"
    cmd = "cloudfox"
    description = "AWS/Azure/GCP cloud enumeration tool"
    category = "recon/cloud"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/BishopFox/cloudfox@latest"
    output_types = [Tag, Vulnerability]

    opts = {
        "profile": OptDef(flag="-p", type=str, help="AWS profile"),
        "region": OptDef(flag="-r", type=str, help="AWS region"),
        "output_dir": OptDef(flag="-o", type=str, help="Output directory"),
        "verbosity": OptDef(flag="-v", type=int, help="Verbosity level"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    subcommand = "aws"

    def _output_suffix(self) -> str:
        return ".txt"

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Tag | Vulnerability]:
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        results: list[Tag | Vulnerability] = []

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            # Check for security findings
            m_finding = _FINDING_RE.search(line)
            if m_finding:
                results.append(
                    Vulnerability(
                        name="Cloud Misconfiguration",
                        matched_at=m_finding.group(1).strip(),
                        severity=Severity.MEDIUM,
                        provider="cloudfox",
                        description=line,
                    )
                )
                continue

            # Parse table rows as tags
            m_row = _TABLE_ROW_RE.match(line)
            if m_row:
                cells = [c.strip() for c in m_row.group(1).split("|")]
                if len(cells) >= 2 and not all(c == "-" * len(c) for c in cells if c):
                    results.append(
                        Tag(
                            name=cells[0],
                            value=" | ".join(cells[1:]),
                            category="cloud_enum",
                        )
                    )

        return results
