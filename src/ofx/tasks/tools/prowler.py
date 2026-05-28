"""prowler — cloud security assessment tool (AWS/Azure/GCP)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry

_SEVERITY_MAP = {
    0: Severity.INFO,
    1: Severity.LOW,
    2: Severity.MEDIUM,
    3: Severity.HIGH,
    4: Severity.CRITICAL,
    "informational": Severity.INFO,
    "low": Severity.LOW,
    "medium": Severity.MEDIUM,
    "high": Severity.HIGH,
    "critical": Severity.CRITICAL,
}


@TaskRegistry.register("prowler")
class ProwlerTask(Task):
    name = "prowler"
    cmd = "prowler"
    description = "Cloud security assessment tool (AWS/Azure/GCP)"
    category = "recon/cloud"
    install_cmd = "uv tool install prowler"
    output_types = [Vulnerability, Tag]

    opts = {
        "provider": OptDef(flag="--provider", type=str, help="Cloud provider"),
        "checks": OptDef(flag="-c", type=str, help="Specific checks to run"),
        "services": OptDef(flag="-s", type=str, help="Services to scan"),
        "severity": OptDef(flag="--severity", type=str, help="Minimum severity"),
        "region": OptDef(flag="-f", type=str, help="AWS region filter"),
        "profile": OptDef(flag="-p", type=str, help="AWS profile"),
        "compliance": OptDef(
            flag="--compliance", type=str, help="Compliance framework"
        ),
        "output_formats": OptDef(flag="-M", type=str, help="Output format"),
        "output_directory": OptDef(flag="-o", type=str, help="Output directory"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["-M", "json-ocsf", "--no-banner"]

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """``prowler <provider>`` — target is the provider name."""
        parts: list[str] = [self.cmd]

        # Target is the cloud provider (aws, azure, gcp)
        if target:
            parts.append(self._q(target))

        parts.extend(self.extra_flags)

        parts.extend(self._build_opt_parts(kwargs))

        return " ".join(parts), None

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability | Tag]:
        raw = self._raw_output(stdout, output_file)
        if not raw:
            return []

        results: list[Vulnerability | Tag] = []

        # Prowler OCSF JSON output can be a JSON array or newline-delimited JSON
        items = self._parse_json_records(raw)

        for item in items:
            severity_id = item.get("severity_id", item.get("severity", ""))
            severity = _SEVERITY_MAP.get(
                severity_id
                if isinstance(severity_id, int)
                else str(severity_id).lower(),
                Severity.MEDIUM,
            )

            status = str(item.get("status", item.get("status_code", ""))).upper()
            if status in ("PASS", "MANUAL"):
                # Only emit tags for passing checks
                check_id = item.get("finding_info", {}).get(
                    "uid", item.get("check_id", "")
                )
                if check_id:
                    results.append(
                        Tag(name=str(check_id), value="PASS", category="cloud_security")
                    )
                continue

            finding_info = item.get("finding_info", {})
            check_title = finding_info.get(
                "title", item.get("check_title", item.get("title", ""))
            )
            check_id = finding_info.get("uid", item.get("check_id", ""))
            resource = (
                str(item.get("resources", [{}])[0].get("uid", ""))
                if item.get("resources")
                else ""
            )
            desc = finding_info.get(
                "desc", item.get("description", item.get("status_extended", ""))
            )

            results.append(
                Vulnerability(
                    name=str(check_title) or str(check_id),
                    id=str(check_id),
                    matched_at=resource,
                    severity=severity,
                    provider="prowler",
                    description=str(desc),
                    extra_data={
                        "status": status,
                        "service": item.get("service", {}).get("name", ""),
                        "region": item.get("region", ""),
                    },
                )
            )

        return results
