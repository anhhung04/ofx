"""john — John the Ripper password cracker."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("john")
class JohnTask(Task):
    name = "john"
    cmd = "john"
    description = "CPU-based password and hash cracking"
    category = "crack/password"
    install_cmd = "apt install -y john"
    output_types = [UserAccount]

    opts = {
        "wordlist": OptDef(flag="--wordlist", type=str, help="Wordlist file"),
        "format": OptDef(
            flag="--format", type=str, help="Hash format (e.g., NT, krb5tgs, krb5asrep)"
        ),
        "rules": OptDef(flag="--rules", type=str, help="Word mangling rules"),
        "show": OptDef(flag="--show", is_flag=True, help="Show cracked passwords"),
        "single": OptDef(flag="--single", is_flag=True, help="Single crack mode"),
        "incremental": OptDef(
            flag="--incremental", is_flag=True, help="Incremental mode"
        ),
        "mask": OptDef(
            flag="--mask", type=str, help="Mask for brute-force (e.g., ?u?l?l?l?d?d)"
        ),
        "fork": OptDef(flag="--fork", type=int, help="Number of parallel processes"),
        "pot": OptDef(flag="--pot", type=str, help="Potfile location"),
        "session": OptDef(flag="--session", type=str, help="Session name"),
        "restore": OptDef(flag="--restore", type=str, help="Restore a session"),
        "max_run_time": OptDef(
            flag="--max-run-time", type=int, help="Max runtime in seconds"
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``john [options] hashfile``."""
        parts: list[str] = [self.cmd]

        parts.extend(self._build_opt_parts(kwargs))

        # Hash file is positional
        parts.append(self._q(target))

        return " ".join(parts), None

    # user:password  (from --show output)
    _SHOW_RE = re.compile(r"^(\S+?):(.*?)(?:::.*)?$")
    # N password hashes cracked, N left
    _SUMMARY_RE = re.compile(r"(\d+) password hash(?:es)? cracked")

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
            if not line or line.startswith("#"):
                continue
            # Skip summary lines
            if self._SUMMARY_RE.search(line):
                continue
            if "password hashes cracked" in line or "Loaded" in line:
                continue

            m = self._SHOW_RE.match(line)
            if m:
                username = m.group(1)
                password = m.group(2)
                if password and username and not username.startswith("("):
                    results.append(
                        UserAccount(
                            username=username,
                            password=password,
                            source="john",
                        )
                    )

        return results
