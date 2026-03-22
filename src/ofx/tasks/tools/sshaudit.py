"""ssh-audit — SSH server and client configuration auditor."""

from __future__ import annotations

import json
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("ssh-audit")
class SshAuditTask(Task):
    name = "ssh-audit"
    cmd = "ssh-audit"
    description = "SSH server and client configuration auditor"
    category = "ssh/audit"
    install_cmd = "uv tool install ssh-audit"
    output_types = [Vulnerability, Tag]

    opts = {
        "port": OptDef(flag="-p", type=int, help="Port number"),
        "timeout": OptDef(flag="-T", type=int, help="Connection timeout in seconds"),
        "level": OptDef(
            flag="-l", type=str, help="Minimum output level: info/warn/fail"
        ),
        "policy": OptDef(
            flag="-P", type=str, help="Policy file to check against"
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["-j"]

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

        results: list[Vulnerability | Tag] = []
        target = data.get("target", "")

        # CVEs
        for cve in data.get("cves", []):
            cvssv2 = self._safe_float(cve.get("cvssv2", 0.0))
            if cvssv2 >= 9.0:
                severity = Severity.CRITICAL
            elif cvssv2 >= 7.0:
                severity = Severity.HIGH
            elif cvssv2 >= 4.0:
                severity = Severity.MEDIUM
            elif cvssv2 > 0:
                severity = Severity.LOW
            else:
                severity = Severity.UNKNOWN

            results.append(
                Vulnerability(
                    name=cve.get("name", ""),
                    id=cve.get("name", ""),
                    severity=severity,
                    matched_at=target,
                    provider="ssh-audit",
                    cvss_score=cvssv2,
                    description=cve.get("description", ""),
                )
            )

        # Weak algorithms (enc, mac, kex)
        for category in ("enc", "mac", "kex"):
            for algo in data.get(category, []):
                if not isinstance(algo, dict):
                    continue
                notes = algo.get("notes", {})
                if notes.get("warn") or notes.get("fail"):
                    results.append(
                        Tag(
                            name=algo.get("algorithm", ""),
                            value="weak",
                            match=target,
                            category=category,
                        )
                    )

        # Banner
        banner_info = data.get("banner", {})
        if isinstance(banner_info, dict):
            raw_banner = banner_info.get("raw", "")
            if raw_banner:
                results.append(
                    Tag(
                        name="ssh_banner",
                        value=raw_banner,
                        match=target,
                        category="banner",
                    )
                )

        return results
