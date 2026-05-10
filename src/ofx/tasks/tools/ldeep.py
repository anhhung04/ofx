"""ldeep — LDAP enumeration for Active Directory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag, UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("ldeep")
class LdeepTask(Task):
    name = "ldeep"
    cmd = "ldeep"
    description = "LDAP Active Directory enumeration"
    category = "ad/enum"
    install_cmd = "uv tool install ldeep"
    output_types = [UserAccount, Tag]

    opts = {
        "username": OptDef(flag="-u", type=str, help="Username"),
        "password": OptDef(flag="-p", type=str, help="Password"),
        "hash": OptDef(flag="-H", type=str, help="NTLM hash"),
        "domain": OptDef(flag="-d", type=str, help="Domain (e.g., corp.local)"),
        "server": OptDef(flag="-s", type=str, help="LDAP server IP"),
        "ssl": OptDef(flag="--ssl", is_flag=True, help="Use LDAPS"),
        "kerberos": OptDef(flag="-k", is_flag=True, help="Use Kerberos authentication"),
        "pfx": OptDef(flag="--pfx", type=str, help="PFX certificate file"),
        "output": OptDef(flag="-o", type=str, help="Output file"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".json"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``ldeep ldap -u user -p pass -d domain -s server {action}``."""
        action = kwargs.pop("action", "users")
        username = kwargs.pop("username", "")
        password = kwargs.pop("password", "")
        domain = kwargs.pop("domain", "")
        server = kwargs.pop("server", target)

        parts: list[str] = [self.cmd, "ldap"]

        if username:
            parts.extend(["-u", username])
        if password:
            parts.extend(["-p", password])
        if domain:
            parts.extend(["-d", domain])
        parts.extend(["-s", server])

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

        parts.append(action)

        return " ".join(parts), None

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[UserAccount | Tag]:
        data = self._read_json_output(stdout, output_file)
        if isinstance(data, list):
            return self._parse_json_list(data)

        # Plain text output — one entry per line
        raw = stdout or ""
        results: list[UserAccount | Tag] = []
        for line in raw.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            # User lines often look like: sAMAccountName
            if "\t" in line or "," in line:
                # Tab-delimited fields
                parts = line.split("\t") if "\t" in line else line.split(",")
                if parts:
                    results.append(
                        UserAccount(username=parts[0].strip(), source="ldeep")
                    )
            else:
                results.append(UserAccount(username=line, source="ldeep"))

        return results

    def _parse_json_list(self, items: list) -> list[UserAccount | Tag]:
        results: list[UserAccount | Tag] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            sam = item.get("sAMAccountName", "")
            if sam:
                results.append(
                    UserAccount(
                        username=sam,
                        domain=item.get("distinguishedName", "")
                        .split(",DC=")[-2]
                        .split(",")[0]
                        if ",DC=" in item.get("distinguishedName", "")
                        else "",
                        source="ldeep",
                        comment=item.get("description", [""])[0]
                        if isinstance(item.get("description"), list)
                        else item.get("description", ""),
                    )
                )
            # ASREQ-roastable
            uac = item.get("userAccountControl", 0)
            if isinstance(uac, int) and uac & 0x400000:
                results.append(Tag(name="asreproastable", value=sam, category="ad"))
        return results
