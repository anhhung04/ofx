"""getTGT — impacket Kerberos TGT request (request a Ticket Granting Ticket)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("gettgt")
class GetTGTTask(Task):
    name = "gettgt"
    cmd = "impacket-getTGT"
    description = "Request a Kerberos Ticket Granting Ticket (TGT)"
    category = "ad/kerberos"
    install_cmd = "uv tool install impacket"
    output_types = [Tag]

    opts = {
        "username": OptDef(flag="-username", type=str, help="Username"),
        "password": OptDef(flag="-password", type=str, help="Password"),
        "hash": OptDef(flag="-hashes", type=str, help="NTLM hashes (LMHASH:NTHASH)"),
        "aesKey": OptDef(flag="-aesKey", type=str, help="AES key for Kerberos auth"),
        "dc_ip": OptDef(flag="-dc-ip", type=str, help="Domain controller IP"),
        "k": OptDef(flag="-k", is_flag=True, help="Use Kerberos authentication"),
        "no_pass": OptDef(flag="-no-pass", is_flag=True, help="Don't ask for password"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".ccache"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``impacket-getTGT domain/user:pass -dc-ip IP``."""
        username = kwargs.pop("username", "")
        password = kwargs.pop("password", "")
        hashes = kwargs.pop("hash", "")
        aes_key = kwargs.pop("aesKey", "")

        parts: list[str] = [self.cmd]
        parts.extend(
            self._build_value_flag_parts(
                [("-hashes", hashes), ("-aesKey", aes_key)]
            )
        )
        parts.extend(self._build_opt_parts(kwargs))

        parts.append(
            self._q(self._domain_user_credential(target, username, password))
        )

        return " ".join(parts), None

    # [*] Saving ticket in user.ccache
    _TICKET_RE = re.compile(r"Saving ticket in\s+(\S+)")

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Tag]:
        raw = self._raw_output(stdout)
        if not raw:
            return []

        results: list[Tag] = []
        for line in raw.splitlines():
            m = self._TICKET_RE.search(line)
            if m:
                results.append(
                    Tag(
                        name="tgt_ccache",
                        value=m.group(1),
                        category="kerberos",
                    )
                )

        return results
