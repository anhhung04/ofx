"""certipy — Active Directory Certificate Services (ADCS) enumeration and exploitation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("certipy")
class CertipyTask(Task):
    name = "certipy"
    cmd = "certipy"
    description = "ADCS enumeration and exploitation (ESC1-ESC8)"
    category = "ad/certs"
    install_cmd = "uv tool install certipy-ad"
    output_types = [Vulnerability, Tag]

    opts = {
        "username": OptDef(flag="-u", type=str, help="Username"),
        "password": OptDef(flag="-p", type=str, help="Password"),
        "hash": OptDef(flag="-hashes", type=str, help="NTLM hashes"),
        "dc_ip": OptDef(flag="-dc-ip", type=str, help="Domain controller IP"),
        "dns_tcp": OptDef(flag="-dns-tcp", is_flag=True, help="Use TCP for DNS"),
        "ns": OptDef(flag="-ns", type=str, help="Nameserver IP"),
        "ca": OptDef(flag="-ca", type=str, help="Certificate Authority name"),
        "template": OptDef(
            flag="-template", type=str, help="Certificate template name"
        ),
        "upn": OptDef(flag="-upn", type=str, help="User Principal Name for ESC1"),
        "pfx": OptDef(flag="-pfx", type=str, help="PFX file for authentication"),
        "output": OptDef(flag="-output", type=str, help="Output file prefix"),
        "json": OptDef(flag="-json", is_flag=True, help="Output in JSON format"),
        "bloodhound": OptDef(
            flag="-bloodhound", is_flag=True, help="Output for BloodHound"
        ),
        "vulnerable": OptDef(
            flag="-vulnerable", is_flag=True, help="Show only vulnerable templates"
        ),
        "enabled": OptDef(
            flag="-enabled", is_flag=True, help="Show only enabled templates"
        ),
        "old_bloodhound": OptDef(
            flag="-old-bloodhound", is_flag=True, help="Output for BloodHound CE < 5.0"
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``certipy find -u user@domain -p pass -dc-ip IP -vulnerable``."""
        mode = kwargs.pop("mode", "find")
        username = kwargs.pop("username", "")
        password = kwargs.pop("password", "")
        hashes = kwargs.pop("hash", "")

        parts: list[str] = [self.cmd, mode]

        if username:
            parts.extend(["-u", self._q(username)])
        if password:
            parts.extend(["-p", self._q(password)])
        if hashes:
            parts.extend(["-hashes", self._q(hashes)])

        parts.extend(self._build_opt_parts(kwargs, skip_keys=["mode", "username", "password", "hash"]))

        # If target looks like an IP for dc-ip, and dc_ip not already set
        if target and "-dc-ip" not in " ".join(parts):
            parts.extend(["-dc-ip", self._q(target)])

        return " ".join(parts), None

    # ESC1: Template 'VulnTemplate' ...
    _ESC_RE = re.compile(r"(ESC\d+)\s*(?:[-:])?\s*(.+)", re.IGNORECASE)
    _TEMPLATE_RE = re.compile(r"Template Name\s*:\s*(.+)", re.IGNORECASE)
    _CA_RE = re.compile(r"CA Name\s*:\s*(.+)", re.IGNORECASE)

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability | Tag]:
        data = self._read_json_output(stdout, output_file)
        if isinstance(data, dict):
            return self._parse_json(data)

        return self._parse_text(stdout or "")

    def _parse_json(self, data: dict) -> list[Vulnerability | Tag]:
        results: list[Vulnerability | Tag] = []
        templates = data.get("Certificate Templates", {})
        for tpl_name, info in templates.items():
            vulns = info.get("Vulnerabilities", {})
            for esc_id, detail in vulns.items():
                results.append(
                    Vulnerability(
                        name=f"ADCS {esc_id}",
                        severity=Severity.HIGH,
                        description=f"Template '{tpl_name}': {detail}"
                        if isinstance(detail, str)
                        else f"Template '{tpl_name}' vulnerable to {esc_id}",
                        provider="certipy",
                    )
                )
            results.append(Tag(name="template", value=tpl_name, category="adcs"))
        return results

    def _parse_text(self, raw: str) -> list[Vulnerability | Tag]:
        results: list[Vulnerability | Tag] = []
        current_template = ""

        for line in raw.splitlines():
            line = line.strip()

            m_tpl = self._TEMPLATE_RE.match(line)
            if m_tpl:
                current_template = m_tpl.group(1).strip()
                results.append(
                    Tag(name="template", value=current_template, category="adcs")
                )
                continue

            m_ca = self._CA_RE.match(line)
            if m_ca:
                results.append(
                    Tag(name="ca", value=m_ca.group(1).strip(), category="adcs")
                )
                continue

            m_esc = self._ESC_RE.match(line)
            if m_esc:
                esc_id = m_esc.group(1).upper()
                detail = m_esc.group(2).strip()
                tpl_ctx = f" (template: {current_template})" if current_template else ""
                results.append(
                    Vulnerability(
                        name=f"ADCS {esc_id}",
                        severity=Severity.HIGH,
                        description=f"{detail}{tpl_ctx}",
                        provider="certipy",
                    )
                )

        return results
