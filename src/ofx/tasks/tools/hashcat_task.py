"""hashcat — GPU-accelerated password cracking."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("hashcat")
class HashcatTask(Task):
    name = "hashcat"
    cmd = "hashcat"
    description = "GPU-accelerated password and hash cracking"
    category = "crack/password"
    install_cmd = "apt install -y hashcat"
    output_types = [UserAccount]

    opts = {
        "hash_type": OptDef(flag="-m", type=int, help="Hash type (e.g., 0=MD5, 1000=NTLM, 13100=Kerberoast, 18200=AS-REP)"),
        "attack_mode": OptDef(flag="-a", type=int, help="Attack mode (0=dict, 1=combo, 3=brute, 6=hybrid, 7=hybrid)"),
        "wordlist": OptDef(flag="--wordlist", type=str, help="Wordlist file path"),
        "rules": OptDef(flag="-r", type=str, help="Rules file"),
        "increment": OptDef(flag="--increment", is_flag=True, help="Enable increment mode"),
        "increment_min": OptDef(flag="--increment-min", type=int, help="Minimum increment length"),
        "increment_max": OptDef(flag="--increment-max", type=int, help="Maximum increment length"),
        "output_file": OptDef(flag="-o", type=str, help="Output file for cracked hashes"),
        "outfile_format": OptDef(flag="--outfile-format", type=int, help="Output format (1-15)"),
        "show": OptDef(flag="--show", is_flag=True, help="Show cracked hashes"),
        "force": OptDef(flag="--force", is_flag=True, help="Ignore warnings"),
        "potfile_disable": OptDef(flag="--potfile-disable", is_flag=True, help="Disable potfile"),
        "status": OptDef(flag="--status", is_flag=True, help="Enable automatic status updates"),
        "status_timer": OptDef(flag="--status-timer", type=int, help="Status update interval (seconds)"),
        "workload": OptDef(flag="-w", type=int, help="Workload profile (1=low, 2=default, 3=high, 4=nightmare)"),
        "device_type": OptDef(flag="-D", type=str, help="Device types (1=CPU, 2=GPU, 3=FPGA)"),
        "username": OptDef(flag="--username", is_flag=True, help="Hash file contains username:hash format"),
        "separator": OptDef(flag="--separator", type=str, help="Separator char for username:hash"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``hashcat -m type hashfile wordlist [options]``."""
        hash_type = kwargs.pop("hash_type", 0)
        attack_mode = kwargs.pop("attack_mode", 0)
        wordlist = kwargs.pop("wordlist", "")

        parts: list[str] = [self.cmd, "-m", str(hash_type), "-a", str(attack_mode)]

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

        # Hash file (target)
        parts.append(target)

        # Wordlist as positional argument
        if wordlist:
            parts.append(wordlist)

        return " ".join(parts), None

    # hash:password  or  user:hash:password
    _CRACKED_RE = re.compile(r"^(.+):(.+)$")

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

            # Standard format: hash:password
            # With --username: user:hash:password
            parts = line.split(":")
            if len(parts) >= 2:
                password = parts[-1]
                # Skip if the "password" looks like a hash component
                if re.match(r"^[a-fA-F0-9]{32}$", password):
                    continue
                username = ""
                hash_val = ""
                if len(parts) >= 3:
                    username = parts[0]
                    hash_val = ":".join(parts[1:-1])
                else:
                    hash_val = parts[0]
                results.append(
                    UserAccount(
                        username=username,
                        password=password,
                        hash=hash_val,
                        source="hashcat",
                    )
                )

        return results
