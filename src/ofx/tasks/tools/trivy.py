"""trivy — comprehensive vulnerability and misconfiguration scanner."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

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
    extra_flags = ["-f", "json", "--quiet"]

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Prepend 'image' subcommand before flags and target."""
        parts: list[str] = [self.cmd, "image", *self.extra_flags]

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

        output_file: Path | None = None
        if self.output_flag:
            output_file = Path(
                tempfile.mkstemp(
                    prefix=f".ofx_task_{self.name}_",
                    suffix=self._output_suffix(),
                )[1]
            )
            parts.extend([self.output_flag, str(output_file)])

        parts.append(target)

        return " ".join(parts), output_file

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability | Tag]:
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
