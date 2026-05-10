"""bloodhound-python — BloodHound data collector for Active Directory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("bloodhound-python")
class BloodhoundPythonTask(Task):
    name = "bloodhound-python"
    cmd = "bloodhound-python"
    description = "Collect Active Directory data for BloodHound analysis"
    category = "ad/enum"
    install_cmd = "uv tool install bloodhound"
    output_types = [Tag]

    opts = {
        "username": OptDef(flag="-u", type=str, help="Username"),
        "password": OptDef(flag="-p", type=str, help="Password"),
        "hash": OptDef(flag="--hashes", type=str, help="NTLM hash (LMHASH:NTHASH)"),
        "domain": OptDef(flag="-d", type=str, help="Domain to enumerate"),
        "dc": OptDef(flag="-dc", type=str, help="Domain controller hostname"),
        "ns": OptDef(flag="-ns", type=str, help="Nameserver for DNS queries"),
        "collection": OptDef(
            flag="-c",
            type=str,
            help="Collection methods (All,Group,Session,Trusts,ACL,...)",
        ),
        "output_dir": OptDef(
            flag="--zip", is_flag=True, help="Compress output into zip"
        ),
        "dns_tcp": OptDef(flag="--dns-tcp", is_flag=True, help="Use TCP for DNS"),
        "dns_timeout": OptDef(
            flag="--dns-timeout", type=int, help="DNS timeout in seconds"
        ),
        "use_ldaps": OptDef(flag="--use-ldaps", is_flag=True, help="Use LDAP over SSL"),
        "auth_method": OptDef(
            flag="-a", type=str, help="Auth method (auto/ntlm/kerberos)"
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".json"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``bloodhound-python -u user -p pass -d domain -dc dc -c All``."""
        parts: list[str] = [self.cmd]

        # If no collection method specified, default to All
        if "collection" not in kwargs:
            kwargs["collection"] = "All"

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

        # Use target as domain if -d not specified
        if "-d" not in " ".join(parts) and target:
            parts.extend(["-d", target])

        return " ".join(parts), None

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Tag]:
        raw = stdout or ""
        results: list[Tag] = []

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # INFO: Done in 00m 05s
            if "Done in" in line:
                results.append(
                    Tag(name="status", value="completed", category="bloodhound")
                )
            # INFO: Found 42 users
            elif "Found" in line:
                results.append(
                    Tag(
                        name="collection_info",
                        value=line.split("INFO:")[-1].strip()
                        if "INFO:" in line
                        else line,
                        category="bloodhound",
                    )
                )
            # Output file names
            elif line.endswith(".json") or line.endswith(".zip"):
                results.append(
                    Tag(name="output_file", value=line, category="bloodhound")
                )

        return results
