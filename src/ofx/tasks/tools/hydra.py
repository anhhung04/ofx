"""hydra — network login brute forcer."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import UserAccount
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("hydra")
class HydraTask(Task):
    name = "hydra"
    cmd = "hydra"
    description = "Network login brute forcer"
    category = "brute/login"
    install_cmd = ""
    output_types = [UserAccount]

    opts = {
        "login": OptDef(flag="-l", type=str, help="Single login name"),
        "login_file": OptDef(flag="-L", type=str, help="File with login names"),
        "password": OptDef(flag="-p", type=str, help="Single password"),
        "password_file": OptDef(flag="-P", type=str, help="File with passwords"),
        "combo_file": OptDef(
            flag="-C", type=str, help="Colon-separated user:pass file"
        ),
        "service": OptDef(flag="--service", type=str, help="Service to attack"),
        "port": OptDef(flag="-s", type=int, help="Port number"),
        "threads": OptDef(flag="-t", type=int, help="Number of parallel tasks"),
        "timeout": OptDef(flag="-w", type=int, help="Timeout per connection (seconds)"),
        "ssl": OptDef(flag="-S", is_flag=True, help="Use SSL"),
        "vV": OptDef(flag="-vV", is_flag=True, help="Verbose mode"),
        "force": OptDef(flag="-f", is_flag=True, help="Stop on first valid pair"),
        "output": OptDef(flag="-o", type=str, help="Output file"),
        "output_format": OptDef(
            flag="-b", type=str, help="Output format (text/json/jsonv1)"
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``hydra [cred opts] {target} {service} [options]``."""
        service = kwargs.pop("service", "ssh")
        parts: list[str] = [self.cmd]

        parts.extend(self._build_opt_parts(kwargs))

        parts.append(self._q(target))
        parts.append(self._q(service))

        return " ".join(parts), None

    _RESULT_RE = re.compile(
        r"\[(\d+)\]\[(\S+)\]\s+host:\s+(\S+)\s+login:\s+(\S+)\s+password:\s+(.*)",
        re.IGNORECASE,
    )

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[UserAccount]:
        raw = self._raw_output(stdout, output_file)
        if not raw:
            return []

        results: list[UserAccount] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            m = self._RESULT_RE.search(line)
            if m:
                results.append(
                    UserAccount(
                        username=m.group(4),
                        password=m.group(5).strip(),
                        host=m.group(3),
                        source="hydra",
                        comment=f"port={m.group(1)} service={m.group(2)}",
                    )
                )

        return results
