"""jwt_tool — JWT vulnerability testing and exploitation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("jwt_tool")
class JwtToolTask(Task):
    name = "jwt_tool"
    cmd = "jwt_tool"
    description = "JWT vulnerability testing and exploitation"
    category = "vuln/jwt"
    install_cmd = (
        "git clone --depth 1 https://github.com/ticarpi/jwt_tool $TOOLS_DIR/jwt_tool"
        " && cd $TOOLS_DIR/jwt_tool && python3 -m pip install -r requirements.txt"
        " && ln -sf $TOOLS_DIR/jwt_tool/jwt_tool.py $TOOLS_BIN_DIR/jwt_tool"
    )
    output_types = [Vulnerability, Tag]

    opts = {
        "mode": OptDef(flag="-M", type=str, help="Mode (at=All Tests, pb=playbook)"),
        "target_url": OptDef(flag="-t", type=str, help="URL to send forged tokens"),
        "cookies": OptDef(flag="-C", type=str, help="Cookies"),
        "headers": OptDef(flag="-rh", type=str, help="Request headers"),
        "exploit": OptDef(
            flag="-X",
            type=str,
            help="Exploit (a=alg:none, n=null sig, k=key confusion, s=spoof JWKS, i=inject)",
        ),
        "verify": OptDef(flag="-V", is_flag=True, help="Verify token only"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``jwt_tool {token} -M {mode} [options]``."""
        mode = kwargs.pop("mode", "at")
        parts: list[str] = [self.cmd, self._q(target), "-M", self._q(mode)]

        parts.extend(self._build_opt_parts(kwargs))

        return " ".join(parts), None

    _VULN_RE = re.compile(
        r"\[\+\]\s*(.*(?:VULNERABILITY|EXPLOITABLE|WEAK).*)", re.IGNORECASE
    )
    _CLAIM_RE = re.compile(r"\[\*\]\s*(\w+)\s*=\s*\"?([^\"]+)\"?")

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
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            m_vuln = self._VULN_RE.search(line)
            if m_vuln:
                vuln_name = m_vuln.group(1).strip()
                if not vuln_name:
                    continue
                results.append(
                    Vulnerability(
                        name=vuln_name,
                        severity=Severity.HIGH,
                        provider="jwt_tool",
                    )
                )
                continue

            m_claim = self._CLAIM_RE.search(line)
            if m_claim:
                results.append(
                    Tag(
                        name="jwt_claim",
                        value=f"{m_claim.group(1)}={m_claim.group(2).strip()}",
                        category="jwt",
                    )
                )
                continue

            if line.startswith("[*]"):
                info = line.split("[*]", 1)[-1].strip()
                if info:
                    results.append(Tag(name="jwt_info", value=info, category="jwt"))

        return results
