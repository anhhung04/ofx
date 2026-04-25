"""scoutsuite — multi-cloud security auditing tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry

_SEVERITY_MAP = {
    "danger": Severity.CRITICAL,
    "warning": Severity.MEDIUM,
    "info": Severity.INFO,
}


@TaskRegistry.register("scoutsuite")
class ScoutsuiteTask(Task):
    name = "scoutsuite"
    cmd = "scout"
    description = "Multi-cloud security auditing tool"
    category = "recon/cloud"
    install_cmd = "uv tool install scoutsuite"
    output_types = [Vulnerability, Tag]

    opts = {
        "profile": OptDef(flag="--profile", type=str, help="Cloud profile name"),
        "regions": OptDef(flag="--regions", type=str, help="Regions to scan"),
        "services": OptDef(flag="--services", type=str, help="Services to audit"),
        "no_browser": OptDef(
            flag="--no-browser", is_flag=True, help="Do not open browser"
        ),
        "result_format": OptDef(flag="--result-format", type=str, help="Result format"),
        "report_dir": OptDef(flag="--report-dir", type=str, help="Report directory"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["--no-browser", "--result-format", "json"]

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """``scout <provider>`` — target is the cloud provider name."""
        parts: list[str] = [self.cmd]

        if target:
            parts.append(target)

        parts.extend(self.extra_flags)

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

        return " ".join(parts), None

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability | Tag]:
        data = self._read_json_output(stdout, output_file)
        if data is None:
            return []

        results: list[Vulnerability | Tag] = []

        # ScoutSuite JSON report has services → service → findings structure
        services = data.get("services", data)
        if not isinstance(services, dict):
            return results

        for svc_name, svc_data in services.items():
            if not isinstance(svc_data, dict):
                continue
            findings = svc_data.get("findings", {})
            if not isinstance(findings, dict):
                continue

            for finding_key, finding in findings.items():
                if not isinstance(finding, dict):
                    continue
                flagged = finding.get("flagged_items", finding.get("items", []))
                level = str(
                    finding.get("level", finding.get("severity", "warning"))
                ).lower()
                desc = finding.get("description", finding.get("rationale", ""))

                if not flagged:
                    continue

                count = (
                    len(flagged)
                    if isinstance(flagged, list)
                    else self._safe_int(flagged)
                )
                results.append(
                    Vulnerability(
                        name=str(finding_key),
                        matched_at=str(svc_name),
                        severity=_SEVERITY_MAP.get(level, Severity.MEDIUM),
                        provider="scoutsuite",
                        description=str(desc),
                        extra_data={
                            "service": svc_name,
                            "flagged_count": count,
                        },
                    )
                )

            # Emit service-level tag
            results.append(Tag(name=svc_name, value="scanned", category="cloud_audit"))

        return results
