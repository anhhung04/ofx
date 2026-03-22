"""grype — vulnerability scanner for container images and filesystems."""

from __future__ import annotations

import json
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Vulnerability
from ofx.tasks.registry import TaskRegistry

_SEVERITY_MAP = {
    "negligible": Severity.INFO,
    "low": Severity.LOW,
    "medium": Severity.MEDIUM,
    "high": Severity.HIGH,
    "critical": Severity.CRITICAL,
}


@TaskRegistry.register("grype")
class GrypeTask(Task):
    name = "grype"
    cmd = "grype"
    description = "Vulnerability scanner for container images and filesystems"
    category = "vuln/scan"
    install_cmd = (
        "curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh"
        " | sh -s -- -b ~/Tools/bin"
    )
    output_types = [Vulnerability]

    opts = {
        "add_cpes": OptDef(
            flag="--add-cpes-if-none",
            is_flag=True,
            help="Generate CPEs if none are present",
        ),
        "by_cve": OptDef(
            flag="--by-cve", is_flag=True, help="Orient results by CVE"
        ),
        "fail_on": OptDef(
            flag="--fail-on",
            type=str,
            help="Fail on severity: negligible/low/medium/high/critical",
        ),
        "only_fixed": OptDef(
            flag="--only-fixed",
            is_flag=True,
            help="Only show vulnerabilities with a fix",
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["-o", "json", "--quiet"]

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability]:
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        matches = data.get("matches", [])
        results: list[Vulnerability] = []

        for match in matches:
            vuln = match.get("vulnerability", {})
            artifact = match.get("artifact", {})
            severity_str = vuln.get("severity", "unknown").lower()
            fix_info = vuln.get("fix", {})

            results.append(
                Vulnerability(
                    name=vuln.get("id", ""),
                    id=vuln.get("id", ""),
                    severity=_SEVERITY_MAP.get(severity_str, Severity.UNKNOWN),
                    matched_at=artifact.get("name", ""),
                    provider="grype",
                    extra_data={
                        "package": artifact.get("name", ""),
                        "version": artifact.get("version", ""),
                        "fix_versions": fix_info.get("versions", []),
                    },
                )
            )

        return results
