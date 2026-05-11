"""kerbrute — Kerberos brute force and user enumeration."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("kerbrute")
class KerbruteTask(Task):
    name = "kerbrute"
    cmd = "kerbrute"
    description = "Kerberos brute force and user enumeration"
    category = "ad/brute"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/ropnop/kerbrute@latest"
    output_types = [UserAccount]

    opts = {
        "mode": OptDef(
            flag="--mode",
            type=str,
            help="Mode (userenum/bruteuser/bruteforce/passwordspray)",
        ),
        "dc": OptDef(flag="--dc", type=str, help="Domain controller IP/hostname"),
        "domain": OptDef(flag="-d", type=str, help="Domain name"),
        "users": OptDef(flag="--users", type=str, help="Path to user wordlist"),
        "password": OptDef(
            flag="--password", type=str, help="Password for passwordspray"
        ),
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "delay": OptDef(flag="--delay", type=int, help="Delay between requests (ms)"),
        "output": OptDef(flag="-o", type=str, help="Output file path"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``kerbrute {mode} --dc {dc} -d {domain} {wordlist}``."""
        mode = kwargs.pop("mode", "userenum")
        dc = kwargs.pop("dc", "")
        domain = kwargs.pop("domain", "")
        users = kwargs.pop("users", "")

        parts: list[str] = [self.cmd, mode]

        if dc:
            parts.extend(["--dc", self._q(dc)])
        if domain:
            parts.extend(["-d", self._q(domain)])

        parts.extend(self._build_opt_parts(kwargs, skip_keys=["mode", "dc", "domain", "users"]))

        # Wordlist or target is positional
        if users:
            parts.append(self._q(users))
        elif target:
            parts.append(self._q(target))

        return " ".join(parts), None

    # [+] VALID USERNAME:	 user@domain.local
    _VALID_USER_RE = re.compile(
        r"\[\+\]\s+VALID USERNAME:\s+(\S+?)@(\S+)", re.IGNORECASE
    )
    # [+] VALID LOGIN:	 user@domain.local:password
    _VALID_LOGIN_RE = re.compile(
        r"\[\+\]\s+VALID LOGIN:\s+(\S+?)@(\S+?):(.+)", re.IGNORECASE
    )

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
            if not line:
                continue

            m_login = self._VALID_LOGIN_RE.search(line)
            if m_login:
                results.append(
                    UserAccount(
                        username=m_login.group(1),
                        domain=m_login.group(2),
                        password=m_login.group(3),
                        source="kerbrute",
                    )
                )
                continue

            m_user = self._VALID_USER_RE.search(line)
            if m_user:
                results.append(
                    UserAccount(
                        username=m_user.group(1),
                        domain=m_user.group(2),
                        source="kerbrute",
                    )
                )

        return results
