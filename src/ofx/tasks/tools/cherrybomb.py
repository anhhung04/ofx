"""cherrybomb — API security scanner for OpenAPI specifications."""

from __future__ import annotations

import re
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
    "info": Severity.INFO,
}

# Match lines like:  Alert: Missing auth  |  Check: BOLA  |  severity: high
_ALERT_RE = re.compile(r"Alert:\s*(.+)", re.IGNORECASE)
_CHECK_RE = re.compile(r"Check:\s*(.+)", re.IGNORECASE)
_SEVERITY_RE = re.compile(
    r"severity:\s*(critical|high|medium|low|info)", re.IGNORECASE
)


@TaskRegistry.register("cherrybomb")
class CherrybombTask(Task):
    name = "cherrybomb"
    cmd = "cherrybomb"
    description = "API security scanner for OpenAPI specifications"
    category = "vuln/api"
    install_cmd = "cargo install cherrybomb"
    output_types = [Vulnerability, Tag]

    opts = {
        "profile": OptDef(flag="--profile", type=str, help="Scan profile"),
        "verbosity": OptDef(flag="-v", is_flag=True, help="Verbose output"),
        "no_color": OptDef(flag="--no-color", is_flag=True, help="Disable colours"),
    }

    input_flag = None
    file_flag = "--file"
    output_flag = None
    silent_flag = "--quiet"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Use ``oas`` subcommand with ``--file`` for the spec file."""
        parts: list[str] = [self.cmd, "oas", "--file", target]
        if self.silent_flag:
            parts.append(self.silent_flag)

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
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        results: list[Vulnerability | Tag] = []
        current_severity = Severity.MEDIUM

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            m_sev = _SEVERITY_RE.search(line)
            if m_sev:
                current_severity = _SEVERITY_MAP.get(
                    m_sev.group(1).lower(), Severity.MEDIUM
                )

            m_alert = _ALERT_RE.search(line)
            if m_alert:
                alert_text = m_alert.group(1).strip()
                if not alert_text:
                    continue
                results.append(
                    Vulnerability(
                        name=alert_text,
                        severity=current_severity,
                        provider="cherrybomb",
                        description=alert_text,
                    )
                )
                current_severity = Severity.MEDIUM
                continue

            m_check = _CHECK_RE.search(line)
            if m_check:
                check_text = m_check.group(1).strip()
                if not check_text:
                    continue
                results.append(
                    Tag(
                        name="check",
                        value=check_text,
                        category="cherrybomb",
                    )
                )

        return results
