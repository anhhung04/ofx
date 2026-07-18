"""linpeas — Linux Privilege Escalation Awesome Script."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("linpeas")
class LinpeasTask(Task):
    name = "linpeas"
    cmd = "linpeas.sh"
    description = "Linux privilege escalation enumeration"
    category = "privesc/linux"
    install_cmd = (
        "curl -fsSL https://github.com/peass-ng/PEASS-ng/releases/latest/download/linpeas.sh "
        "-o $TOOLS_BIN_DIR/linpeas.sh && chmod +x $TOOLS_BIN_DIR/linpeas.sh"
    )
    output_types = [Vulnerability, Tag]

    opts = {
        "quiet": OptDef(flag="-q", is_flag=True, help="Quiet mode (less output)"),
        "thorough": OptDef(flag="-a", is_flag=True, help="All checks (thorough)"),
        "no_network": OptDef(flag="-N", is_flag=True, help="Skip network checks"),
        "password": OptDef(flag="-P", type=str, help="Test sudo with this password"),
        "checks": OptDef(
            flag="-s",
            type=str,
            help="Specific check sections (SysI,Devs,Net,UsrI,SofI,ProCronSrworworworwo...)",
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``linpeas.sh [options]``. Target is ignored (runs locally)."""
        parts: list[str] = [self.cmd]

        parts.extend(self._build_opt_parts(kwargs))

        return " ".join(parts), None

    _PE_RE = re.compile(r"\[!\]\s*(\d+%\s+PE.*|.*CVE-\d{4}-\d+.*)", re.IGNORECASE)
    _SUID_RE = re.compile(r"^-[rw]s", re.IGNORECASE)
    _WRITABLE_RE = re.compile(r"You can write (.*)", re.IGNORECASE)
    _CVE_RE = re.compile(r"(CVE-\d{4}-\d+)", re.IGNORECASE)

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
        seen_cves: set[str] = set()

        for line in raw.splitlines():
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
            if not clean:
                continue

            for m in self._CVE_RE.finditer(clean):
                cve = m.group(1).upper()
                if cve not in seen_cves:
                    seen_cves.add(cve)
                    results.append(
                        Vulnerability(
                            name=cve,
                            severity=Severity.HIGH,
                            description=clean,
                            provider="linpeas",
                        )
                    )

            m_pe = self._PE_RE.search(clean)
            if m_pe and not any(c in clean for c in seen_cves):
                results.append(
                    Tag(name="pe_vector", value=clean[:200], category="privesc")
                )

        return results
