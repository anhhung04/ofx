"""trivy — comprehensive vulnerability and misconfiguration scanner."""

from __future__ import annotations

from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry

_SEVERITY_MAP = {
    "low": Severity.LOW,
    "medium": Severity.MEDIUM,
    "high": Severity.HIGH,
    "critical": Severity.CRITICAL,
    "unknown": Severity.UNKNOWN,
}


@TaskRegistry.register("trivy")
class TrivyTask(Task):
    name = "trivy"
    cmd = "trivy"
    description = "Comprehensive vulnerability and misconfiguration scanner"
    category = "vuln/scan"
    install_cmd = (
        "curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main"
        "/contrib/install.sh | sh -s -- -b ~/Tools/bin"
    )
    output_types = [Vulnerability, Tag]

    opts = {
        "severity": OptDef(
            flag="--severity",
            type=str,
            help="Filter by severity CRITICAL,HIGH,MEDIUM,LOW",
        ),
        "ignore_unfixed": OptDef(
            flag="--ignore-unfixed",
            is_flag=True,
            help="Ignore unfixed vulnerabilities",
        ),
        "scanners": OptDef(
            flag="--scanners",
            type=str,
            help="Scanners to use: vuln,misconfig,secret,license",
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    subcommand = "image"
    extra_flags = ["-f", "json"]
    silent_flag = "--quiet"

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability | Tag]:
        data = self._read_json_output(stdout, output_file)
        if data is None:
            return []

        scan_results = data.get("Results", [])
        results: list[Vulnerability | Tag] = []

        for result in scan_results:
            target_name = result.get("Target", "")
            scan_class = result.get("Class", "")
            scan_type = result.get("Type", "")

            if scan_class or scan_type:
                results.append(
                    Tag(
                        name=scan_class or scan_type,
                        value=scan_type,
                        match=target_name,
                        category="scan",
                    )
                )

            for vuln in result.get("Vulnerabilities", []):
                vuln_id = vuln.get("VulnerabilityID", "")
                if not vuln_id:
                    continue
                severity_str = vuln.get("Severity", "unknown").lower()
                results.append(
                    Vulnerability(
                        name=vuln_id,
                        id=vuln_id,
                        severity=_SEVERITY_MAP.get(severity_str, Severity.UNKNOWN),
                        matched_at=vuln.get("PkgName", ""),
                        provider="trivy",
                        extra_data={
                            "package": vuln.get("PkgName"),
                            "installed": vuln.get("InstalledVersion"),
                            "fixed": vuln.get("FixedVersion"),
                        },
                    )
                )

        return results
