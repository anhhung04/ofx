"""linpeas — Linux Privilege Escalation Awesome Script."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("linpeas")
class LinpeasTask(Task):
    name = "linpeas"
    cmd = "linpeas.sh"
    description = "Linux privilege escalation enumeration"
    category = "privesc/linux"
    install_cmd = (
        "curl -fsSL https://github.com/peass-ng/PEASS-ng/releases/latest/download/linpeas.sh "
        "-o ~/Tools/bin/linpeas.sh && chmod +x ~/Tools/bin/linpeas.sh"
    )
    output_types = [Vulnerability, Tag]

    opts = {
        "quiet": OptDef(flag="-q", is_flag=True, help="Quiet mode (less output)"),
        "thorough": OptDef(flag="-a", is_flag=True, help="All checks (thorough)"),
        "no_network": OptDef(flag="-N", is_flag=True, help="Skip network checks"),
        "password": OptDef(flag="-P", type=str, help="Test sudo with this password"),
        "checks": OptDef(flag="-s", type=str, help="Specific check sections (SysI,Devs,Net,UsrI,SofI,ProCronSrworworworwo...)"),
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

    # ╔══════════╗ pattern or [!] 95% PE vectors
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

            # CVE references
            for m in self._CVE_RE.finditer(clean):
                cve = m.group(1).upper()
                if cve not in seen_cves:
                    seen_cves.add(cve)
                    results.append(
                        Vulnerability(
                            name=cve,
                            url="",
                            severity="high",
                            description=clean,
                            source="linpeas",
                        )
                    )

            # PE vectors
            m_pe = self._PE_RE.search(clean)
            if m_pe and not any(c in clean for c in seen_cves):
                results.append(
                    Tag(name="pe_vector", value=clean[:200], category="privesc")
                )

        return results
