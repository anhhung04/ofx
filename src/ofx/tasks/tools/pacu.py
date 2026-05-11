"""pacu — AWS exploitation framework."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry

_PRIVESC_RE = re.compile(
    r"(?:privilege\s*escalation|privesc|escalat)",
    re.IGNORECASE,
)
_MISCONFIG_RE = re.compile(
    r"(?:misconfigur|overly\s*permissive|public\s*access|exposed|vulnerable)",
    re.IGNORECASE,
)
_DATA_RE = re.compile(
    r"(?:found|discovered|enumerated|collected)\s+(\d+)\s+(.+)",
    re.IGNORECASE,
)


@TaskRegistry.register("pacu")
class PacuTask(Task):
    name = "pacu"
    cmd = "pacu"
    description = "AWS exploitation framework"
    category = "exploit/cloud"
    install_cmd = "uv tool install pacu"
    output_types = [Vulnerability, Tag]

    opts = {
        "module": OptDef(flag="--module", type=str, help="Module to run"),
        "module_args": OptDef(flag="--module-args", type=str, help="Module arguments"),
        "session": OptDef(flag="--session", type=str, help="Session name"),
        "set_regions": OptDef(flag="--set-regions", type=str, help="AWS regions"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["--cli"]

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """``pacu --cli --module <target>`` — target is the module name."""
        parts: list[str] = [self.cmd, *self.extra_flags]

        # Target is the module name
        if target and "module" not in kwargs:
            parts.extend(["--module", self._q(target)])

        parts.extend(self._build_opt_parts(kwargs))

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

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            if _PRIVESC_RE.search(line):
                results.append(
                    Vulnerability(
                        name="AWS Privilege Escalation",
                        matched_at=line[:120],
                        severity=Severity.CRITICAL,
                        provider="pacu",
                        description=line,
                    )
                )
                continue

            if _MISCONFIG_RE.search(line):
                results.append(
                    Vulnerability(
                        name="AWS Misconfiguration",
                        matched_at=line[:120],
                        severity=Severity.HIGH,
                        provider="pacu",
                        description=line,
                    )
                )
                continue

            m_data = _DATA_RE.search(line)
            if m_data:
                results.append(
                    Tag(
                        name=m_data.group(2).strip(),
                        value=m_data.group(1),
                        category="aws_enum",
                    )
                )

        return results
