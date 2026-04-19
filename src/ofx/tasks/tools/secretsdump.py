"""secretsdump — impacket credential dumping from SAM/LSA/NTDS."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("secretsdump")
class SecretsdumpTask(Task):
    name = "secretsdump"
    cmd = "impacket-secretsdump"
    description = "Dump credentials from SAM, LSA secrets, and NTDS.dit"
    category = "ad/creds"
    install_cmd = "uv tool install impacket"
    output_types = [UserAccount]

    opts = {
        "username": OptDef(flag="-username", type=str, help="Username for authentication"),
        "password": OptDef(flag="-password", type=str, help="Password"),
        "hash": OptDef(flag="-hashes", type=str, help="NTLM hashes (LMHASH:NTHASH)"),
        "domain": OptDef(flag="-domain", type=str, help="Domain name"),
        "dc_ip": OptDef(flag="-dc-ip", type=str, help="Domain controller IP"),
        "just_dc": OptDef(flag="-just-dc", is_flag=True, help="Extract only NTDS.dit data (DRSUAPI)"),
        "just_dc_ntlm": OptDef(flag="-just-dc-ntlm", is_flag=True, help="Extract only NTLM hashes from NTDS"),
        "just_dc_user": OptDef(flag="-just-dc-user", type=str, help="Extract data for specific user only"),
        "sam": OptDef(flag="-sam", is_flag=True, help="Dump local SAM hashes"),
        "system": OptDef(flag="-system", type=str, help="Path to SYSTEM hive"),
        "ntds": OptDef(flag="-ntds", type=str, help="Path to NTDS.dit file"),
        "use_vss": OptDef(flag="-use-vss", is_flag=True, help="Use VSS method instead of DRSUAPI"),
        "exec_method": OptDef(flag="-exec-method", type=str, help="Remote exec method (smbexec/wmiexec/mmcexec)"),
        "output_file": OptDef(flag="-outputfile", type=str, help="Base name for output files"),
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
        """Build: ``impacket-secretsdump [domain/]user[:pass]@target [options]``."""
        username = kwargs.pop("username", "")
        password = kwargs.pop("password", "")
        hashes = kwargs.pop("hash", "")
        domain = kwargs.pop("domain", "")

        parts: list[str] = [self.cmd]

        if hashes:
            parts.extend(["-hashes", hashes])
        if kwargs.pop("just_dc", False):
            parts.append("-just-dc")
        if kwargs.pop("just_dc_ntlm", False):
            parts.append("-just-dc-ntlm")

        just_dc_user = kwargs.pop("just_dc_user", "")
        if just_dc_user:
            parts.extend(["-just-dc-user", just_dc_user])

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

        # Build credential string: domain/user:pass@target
        cred = ""
        if domain:
            cred += f"{domain}/"
        if username:
            cred += username
            if password:
                cred += f":{password}"
        cred += f"@{target}"
        parts.append(cred)

        return " ".join(parts), None

    # Administrator:500:aad3b435...:31d6cfe0...:::
    _NTDS_RE = re.compile(r"^(.+?):(\d+):([a-fA-F0-9]{32}):([a-fA-F0-9]{32}):::")

    # domain\user:plain_password_here
    _CLEARTEXT_RE = re.compile(r"^(?:(\S+?)\\)?(\S+?):(.+)$")

    # $MACHINE.ACC: ... :aad3b435...:hash:::
    _MACHINE_RE = re.compile(r"^\$MACHINE\.ACC:", re.IGNORECASE)

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
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("[") or line.startswith("Impacket"):
                continue
            if self._MACHINE_RE.match(line):
                continue

            m = self._NTDS_RE.match(line)
            if m:
                username = m.group(1)
                domain = ""
                if "\\" in username:
                    domain, username = username.split("\\", 1)
                results.append(
                    UserAccount(
                        username=username,
                        hash=f"{m.group(3)}:{m.group(4)}",
                        domain=domain,
                        source="secretsdump",
                        comment=f"RID:{m.group(2)}",
                    )
                )
                continue

        return results
