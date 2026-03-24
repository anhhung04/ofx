"""brutespray — automated service password spraying."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Port, UserAccount
from ofx.tasks.registry import TaskRegistry

# Matches: [+] SUCCESS: ssh://user:pass@host:22
_SUCCESS_RE = re.compile(
    r"\[\+\]\s*SUCCESS[:\s]*"
    r"(?:(?P<service>\w+)://)?"
    r"(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)"
)


@TaskRegistry.register("brutespray")
class BrutesprayTask(Task):
    name = "brutespray"
    cmd = "brutespray"
    description = "Automated service password spraying from scan output"
    category = "brute/spray"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/x90skysn3k/brutespray@latest"
    output_types = [UserAccount, Port]

    opts = {
        "port": OptDef(flag="-p", type=int, help="Target port"),
        "service": OptDef(flag="-s", type=str, help="Target service"),
        "username": OptDef(flag="-u", type=str, help="Single username"),
        "password": OptDef(flag="-P", type=str, help="Single password"),
        "threads": OptDef(flag="-t", type=int, help="Threads per host"),
        "concurrent_hosts": OptDef(flag="-T", type=int, help="Concurrent hosts"),
        "user_file": OptDef(flag="-U", type=str, help="Username wordlist file"),
        "pass_file": OptDef(flag="-PF", type=str, help="Password wordlist file"),
    }

    input_flag = "-H"
    file_flag = "-f"
    output_flag = None
    extra_flags = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Handle host vs. file target and map options."""
        parts: list[str] = [self.cmd, *self.extra_flags]

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

        if target and not target.startswith("http") and Path(target).is_file():
            parts.extend(["-f", target])
        elif target:
            parts.extend(["-H", target])

        return " ".join(parts), None

    def parse_line(self, line: str) -> list[UserAccount | Port]:
        line = line.strip()
        if not line:
            return []

        match = _SUCCESS_RE.search(line)
        if not match:
            return []

        service = match.group("service") or ""
        user = match.group("user")
        password = match.group("password")
        host = match.group("host")
        port = self._safe_int(match.group("port"))

        results: list[UserAccount | Port] = [
            UserAccount(
                username=user,
                password=password,
                host=host,
                source="brutespray",
                comment=f"{service}://{host}:{port}" if service else f"{host}:{port}",
            ),
            Port(
                port=port,
                ip=host,
                host=host,
                service_name=service,
                state="open",
            ),
        ]

        return results

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[UserAccount | Port]:
        results: list[UserAccount | Port] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results
