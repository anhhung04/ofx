"""getST — impacket Kerberos Service Ticket request (S4U2Self / S4U2Proxy)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("getst")
class GetSTTask(Task):
    name = "getst"
    cmd = "impacket-getST"
    description = "Request Kerberos Service Ticket via S4U2Self/S4U2Proxy"
    category = "ad/kerberos"
    install_cmd = "uv tool install impacket"
    output_types = [Tag]

    opts = {
        "username": OptDef(flag="-username", type=str, help="Username"),
        "password": OptDef(flag="-password", type=str, help="Password"),
        "hash": OptDef(flag="-hashes", type=str, help="NTLM hashes (LMHASH:NTHASH)"),
        "aesKey": OptDef(flag="-aesKey", type=str, help="AES key"),
        "dc_ip": OptDef(flag="-dc-ip", type=str, help="Domain controller IP"),
        "spn": OptDef(flag="-spn", type=str, help="Target SPN (e.g., cifs/host)"),
        "impersonate": OptDef(
            flag="-impersonate", type=str, help="User to impersonate"
        ),
        "altservice": OptDef(
            flag="-altservice", type=str, help="Substitute service in ticket"
        ),
        "self_": OptDef(flag="-self", is_flag=True, help="Perform S4U2Self only"),
        "additional_ticket": OptDef(
            flag="-additional-ticket", type=str, help="Additional ticket for S4U2Proxy"
        ),
        "k": OptDef(flag="-k", is_flag=True, help="Use Kerberos authentication"),
        "no_pass": OptDef(flag="-no-pass", is_flag=True, help="Don't ask for password"),
        "force_forwardable": OptDef(
            flag="-force-forwardable",
            is_flag=True,
            help="Force ticket to be forwardable",
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".ccache"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``impacket-getST domain/user:pass -spn cifs/host -impersonate admin``."""
        username = kwargs.pop("username", "")
        password = kwargs.pop("password", "")
        hashes = kwargs.pop("hash", "")
        aes_key = kwargs.pop("aesKey", "")

        parts: list[str] = [self.cmd]

        if hashes:
            parts.extend(["-hashes", hashes])
        if aes_key:
            parts.extend(["-aesKey", aes_key])

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

        cred = target
        if username:
            cred += f"/{username}"
            if password:
                cred += f":{password}"
        parts.append(cred)

        return " ".join(parts), None

    _TICKET_RE = re.compile(r"Saving ticket in\s+(\S+)")

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Tag]:
        raw = stdout or ""
        results: list[Tag] = []
        for line in raw.splitlines():
            m = self._TICKET_RE.search(line)
            if m:
                results.append(
                    Tag(name="st_ccache", value=m.group(1), category="kerberos")
                )
        return results
