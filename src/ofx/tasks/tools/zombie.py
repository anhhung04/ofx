"""zombie — lightweight service credential brute-forcer by chainreactors.

Designed for seamless chaining with gogo: pass gogo's result file via
``--gogo`` (``-g``) to auto-extract targets with service information.

Usage in OFX workflows::

    - task: gogo
      name: scan-network
      with:
        target: "{{ inputs.target }}"
        ports: "top2,win,db"

    - task: zombie
      name: brute-services
      with:
        gogo: "{{ steps['scan-network'].outputs.output_file }}"
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("zombie")
class ZombieTask(Task):
    name = "zombie"
    cmd = "zombie"
    description = "Lightweight service credential brute-forcer with gogo integration"
    category = "brute/login"
    install_cmd = (
        "GOBIN=$TOOLS_BIN_DIR go install -v github.com/chainreactors/zombie@latest"
    )
    output_types = [UserAccount]

    opts = {
        "user": OptDef(flag="-u", type=str, help="Single username"),
        "user_file": OptDef(flag="-U", type=str, help="File with usernames"),
        "password": OptDef(flag="-p", type=str, help="Single password"),
        "password_file": OptDef(flag="-P", type=str, help="File with passwords"),
        "auth": OptDef(flag="-a", type=str, help="Auth pair (user::pass)"),
        "auth_file": OptDef(flag="-A", type=str, help="File with auth pairs"),
        "service": OptDef(
            flag="-s", type=str, help="Service name (ssh,mysql,smb,rdp,ftp,...)"
        ),
        "filter_service": OptDef(
            flag="-S", type=str, help="Filter services from gogo/json input"
        ),
        "gogo": OptDef(
            flag="-g", type=str, help="Gogo result file (.dat/.dat1) for chaining"
        ),
        "json_input": OptDef(flag="-j", type=str, help="JSON result file input"),
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "timeout": OptDef(
            flag="--timeout", type=int, help="Connection timeout in seconds"
        ),
        "mode": OptDef(flag="-m", type=str, help="Attack mode (clusterbomb/sniper)"),
        "weakpass": OptDef(
            flag="--weakpass", is_flag=True, help="Generate common weak passwords"
        ),
        "force_continue": OptDef(
            flag="--force-continue",
            is_flag=True,
            help="Don't stop after first success per host",
        ),
        "no_unauth": OptDef(flag="--no-unauth", is_flag=True, help="Skip unauth check"),
        "no_honeypot": OptDef(
            flag="--no-honeypot", is_flag=True, help="Skip honeypot check"
        ),
        "top": OptDef(flag="--top", type=int, help="Use top N passwords only"),
        "userrule": OptDef(
            flag="--userrule", type=str, help="Username generator rule file"
        ),
        "pwdrule": OptDef(
            flag="--pwdrule", type=str, help="Password generator rule file"
        ),
        "param": OptDef(flag="--param", type=str, help="Service-specific parameters"),
        "bar": OptDef(flag="--bar", is_flag=True, help="Show progress bar"),
    }

    input_flag = "-i"
    file_flag = "-I"
    output_flag = "-f"
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".json"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build zombie command.

        When ``gogo`` kwarg is set, zombie reads targets + service info
        directly from gogo's compressed result file (``-g file``).
        The ``target`` is still required by OFX but unused in gogo mode.
        """
        gogo_file = kwargs.pop("gogo", None)
        json_input = kwargs.pop("json_input", None)

        parts: list[str] = [self.cmd]

        parts.extend(self._build_opt_parts(kwargs))

        output_file = self._make_output_path()
        parts.extend(["-f", str(output_file), "-O", "json"])

        if gogo_file:
            parts.extend(["-g", self._q(gogo_file)])
        elif json_input:
            parts.extend(["-j", self._q(json_input)])
        elif target:
            target_is_file = not target.startswith("http") and Path(target).is_file()
            if target_is_file:
                parts.extend([self.file_flag, self._q(target)])
            else:
                parts.extend([self.input_flag, self._q(target)])
        else:
            raise ValueError("zombie requires a target, --gogo file, or --json file")

        return " ".join(parts), output_file

    # zombie JSON output: {"host":"1.1.1.1","port":22,"service":"ssh","user":"root","password":"toor","status":"success"}
    # Also supports: string format "service://user:password@host:port"
    _STRING_RE = re.compile(
        r"(?P<service>\w+)://(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)"
    )

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[UserAccount]:
        results: list[UserAccount] = []

        raw = self._raw_output(stdout, output_file)
        if not raw:
            return results

        # Try full JSON array/object first.
        json_output = self._read_json_output(raw)
        if isinstance(json_output, list):
            for entry in json_output:
                if not isinstance(entry, dict):
                    continue
                acct = self._parse_json_entry(entry)
                if acct:
                    results.append(acct)
            return results
        if isinstance(json_output, dict):
            acct = self._parse_json_entry(json_output)
            return [acct] if acct else []

        # Fall back to line-by-line
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            # Try JSON line
            if line.startswith("{"):
                entry = self._parse_json_line(line)
                if entry is not None:
                    acct = self._parse_json_entry(entry)
                    if acct:
                        results.append(acct)
                    continue

            # Try string format
            m = self._STRING_RE.search(line)
            if m:
                results.append(
                    UserAccount(
                        username=m.group("user"),
                        password=m.group("password"),
                        host=m.group("host"),
                        source="zombie",
                        comment=f"service={m.group('service')} port={m.group('port')}",
                    )
                )

        return results

    def _parse_json_entry(self, entry: dict) -> UserAccount | None:
        """Parse a single zombie JSON result entry."""
        host = entry.get("host", entry.get("ip", ""))
        user = entry.get("user", entry.get("username", ""))
        password = entry.get("password", entry.get("pass", ""))
        service = entry.get("service", entry.get("protocol", ""))
        port = self._safe_int(entry.get("port", 0))
        status = entry.get("status", "")

        if not host or not user:
            return None

        # Only include successful results
        if status and status.lower() not in ("success", "ok", ""):
            return None

        comment_parts = []
        if service:
            comment_parts.append(f"service={service}")
        if port:
            comment_parts.append(f"port={port}")

        return UserAccount(
            username=user,
            password=password,
            host=host,
            source="zombie",
            comment=" ".join(comment_parts),
        )
