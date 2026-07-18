"""netexec — network service pentesting (CrackMapExec successor)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag, UserAccount
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("netexec")
class NetexecTask(Task):
    name = "netexec"
    cmd = "nxc"
    description = "Network service pentesting (CrackMapExec successor)"
    category = "ad/enum"
    install_cmd = "uv tool install netexec"
    output_types = [UserAccount, Tag]

    opts = {
        "protocol": OptDef(
            flag="--protocol",
            type=str,
            help="Protocol (smb/ldap/winrm/ssh/mssql/rdp/ftp)",
        ),
        "username": OptDef(flag="-u", type=str, help="Username"),
        "password": OptDef(flag="-p", type=str, help="Password"),
        "hash": OptDef(flag="-H", type=str, help="NTLM hash"),
        "domain": OptDef(flag="-d", type=str, help="Domain name"),
        "shares": OptDef(flag="--shares", is_flag=True, help="Enumerate shares"),
        "users": OptDef(flag="--users", is_flag=True, help="Enumerate users"),
        "groups": OptDef(flag="--groups", is_flag=True, help="Enumerate groups"),
        "sessions": OptDef(flag="--sessions", is_flag=True, help="Enumerate sessions"),
        "loggedon_users": OptDef(
            flag="--loggedon-users", is_flag=True, help="Enumerate logged-on users"
        ),
        "pass_pol": OptDef(
            flag="--pass-pol", is_flag=True, help="Dump password policy"
        ),
        "rid_brute": OptDef(flag="--rid-brute", is_flag=True, help="RID brute force"),
        "local_auth": OptDef(
            flag="--local-auth", is_flag=True, help="Use local authentication"
        ),
        "sam": OptDef(flag="--sam", is_flag=True, help="Dump SAM hashes"),
        "lsa": OptDef(flag="--lsa", is_flag=True, help="Dump LSA secrets"),
        "ntds": OptDef(flag="--ntds", is_flag=True, help="Dump NTDS.dit"),
        "exec_method": OptDef(flag="--exec-method", type=str, help="Execution method"),
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "module": OptDef(flag="-M", type=str, help="Module to run"),
        "module_option": OptDef(flag="-o", type=str, help="Module option (KEY=VALUE)"),
        "gen_relay_list": OptDef(
            flag="--gen-relay-list", type=str, help="Output file for SMB relay targets"
        ),
        "asreproast": OptDef(
            flag="--asreproast", type=str, help="Output file for AS-REP roast hashes"
        ),
        "gmsa": OptDef(flag="--gmsa", is_flag=True, help="Dump gMSA passwords"),
        "dpapi": OptDef(flag="--dpapi", is_flag=True, help="Dump DPAPI credentials"),
        "kerberoasting": OptDef(
            flag="--kerberoasting", type=str, help="Output file for Kerberoast hashes"
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``nxc {protocol} {target} [options]``."""
        protocol = kwargs.pop("protocol", "smb")
        parts: list[str] = [self.cmd, protocol, self._q(target)]

        parts.extend(self._build_opt_parts(kwargs))

        return " ".join(parts), None

    _SUCCESS_RE = re.compile(
        r"\[\+\]\s+(?:(\S+)\\)?(\S+?)(?::(\S+))?\s*(\(Pwn3d!\))?\s*$"
    )
    _USER_RE = re.compile(r"^\S+\s+\d+\s+\S+\s+(.+?)\s+rid:\s*(\d+)", re.IGNORECASE)
    _SHARE_RE = re.compile(
        r"^\S+\s+\d+\s+\S+\s+(\S+)\s+(READ|WRITE|NO ACCESS)", re.IGNORECASE
    )

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[UserAccount | Tag]:
        raw = self._raw_output(stdout, output_file)
        if not raw:
            return []

        results: list[UserAccount | Tag] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            if "[-]" in line and "STATUS_LOGON_FAILURE" in line:
                continue

            m = self._SUCCESS_RE.search(line)
            if m and "[+]" in line:
                domain = m.group(1) or ""
                user = m.group(2)
                secret = m.group(3) or ""
                pwned = bool(m.group(4))
                results.append(
                    UserAccount(
                        username=user,
                        password=secret if ":" not in secret else "",
                        hash=secret if ":" in secret else "",
                        domain=domain,
                        privilege_level="admin" if pwned else "",
                        source="netexec",
                    )
                )
                continue

            m_user = self._USER_RE.match(line)
            if m_user:
                results.append(
                    UserAccount(
                        username=m_user.group(1).strip(),
                        source="netexec",
                        comment=f"RID:{m_user.group(2)}",
                    )
                )
                continue

            m_share = self._SHARE_RE.match(line)
            if m_share:
                results.append(
                    Tag(
                        name="share",
                        value=m_share.group(1),
                        category="ad",
                    )
                )
                continue

            if "[*]" in line:
                info = line.split("[*]", 1)[-1].strip()
                if info:
                    results.append(Tag(name="info", value=info, category="ad"))

        return results
