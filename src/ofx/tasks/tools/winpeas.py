"""winpeas — Windows Privilege Escalation Awesome Script."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("winpeas")
class WinpeasTask(Task):
    name = "winpeas"
    cmd = "winPEASx64.exe"
    description = "Windows privilege escalation enumeration"
    category = "privesc/windows"
    install_cmd = (
        "curl -fsSL https://github.com/peass-ng/PEASS-ng/releases/latest/download/winPEASx64.exe "
        "-o $TOOLS_BIN_DIR/winPEASx64.exe"
    )
    output_types = [Vulnerability, Tag]

    opts = {
        "quiet": OptDef(flag="quiet", is_flag=True, help="Quiet mode"),
        "checks": OptDef(flag="--checks", type=str, help="Specific checks to run"),
        "log": OptDef(flag="log", is_flag=True, help="Log output to file"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``winPEASx64.exe [options]``. Target is ignored (runs locally)."""
        parts: list[str] = [self.cmd]

        parts.extend(self._build_opt_parts(kwargs))

        return " ".join(parts), None

    _CVE_RE = re.compile(r"(CVE-\d{4}-\d+)", re.IGNORECASE)

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
                            provider="winpeas",
                        )
                    )

        return results
