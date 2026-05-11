"""ldapdomaindump — LDAP domain information dumper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag, UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("ldapdomaindump")
class LdapDomainDumpTask(Task):
    name = "ldapdomaindump"
    cmd = "ldapdomaindump"
    description = "Dump LDAP domain information (users, groups, computers, policies)"
    category = "ad/enum"
    install_cmd = "uv tool install ldapdomaindump"
    output_types = [UserAccount, Tag]

    opts = {
        "username": OptDef(flag="-u", type=str, help="Username (DOMAIN\\user)"),
        "password": OptDef(flag="-p", type=str, help="Password"),
        "at": OptDef(flag="-at", type=str, help="Auth type (NTLM/SIMPLE)"),
        "output_dir": OptDef(flag="-o", type=str, help="Output directory"),
        "no_html": OptDef(flag="--no-html", is_flag=True, help="Skip HTML output"),
        "no_json": OptDef(flag="--no-json", is_flag=True, help="Skip JSON output"),
        "no_grep": OptDef(flag="--no-grep", is_flag=True, help="Skip grep-able output"),
        "minimal": OptDef(flag="-m", is_flag=True, help="Only dump minimal info"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".json"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``ldapdomaindump -u 'DOMAIN\\user' -p pass ldap://target``."""
        parts: list[str] = [self.cmd]

        parts.extend(self._build_opt_parts(kwargs))

        # Target as LDAP URI
        if not target.startswith("ldap"):
            target = f"ldap://{target}"
        parts.append(self._q(target))

        return " ".join(parts), None

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[UserAccount | Tag]:
        data = self._read_json_output(stdout, output_file)
        if isinstance(data, list):
            return self._parse_entries(data)

        raw = stdout or ""
        results: list[UserAccount | Tag] = []
        for line in raw.strip().splitlines():
            line = line.strip()
            if "Writing" in line and "to" in line:
                results.append(Tag(name="output_file", value=line, category="ldap"))
        return results

    def _parse_entries(self, entries: list) -> list[UserAccount | Tag]:
        results: list[UserAccount | Tag] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            attrs = entry.get("attributes", entry)
            sam = attrs.get("sAMAccountName", "")
            if isinstance(sam, list):
                sam = sam[0] if sam else ""
            if sam:
                results.append(UserAccount(username=sam, source="ldapdomaindump"))
        return results
