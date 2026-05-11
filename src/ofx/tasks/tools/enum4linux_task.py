"""enum4linux-ng — SMB/AD enumeration tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag, UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("enum4linux")
class Enum4linuxTask(Task):
    name = "enum4linux"
    cmd = "enum4linux-ng"
    description = "SMB/AD enumeration tool"
    category = "ad/enum"
    install_cmd = "uv tool install git+https://github.com/cddmp/enum4linux-ng"
    output_types = [UserAccount, Tag]

    opts = {
        "username": OptDef(flag="-u", type=str, help="Username"),
        "password": OptDef(flag="-p", type=str, help="Password"),
        "domain": OptDef(flag="-d", type=str, help="Domain"),
        "users": OptDef(flag="-U", is_flag=True, help="Enumerate users"),
        "shares": OptDef(flag="-S", is_flag=True, help="Enumerate shares"),
        "groups": OptDef(flag="-G", is_flag=True, help="Enumerate groups"),
        "policies": OptDef(flag="-P", is_flag=True, help="Enumerate password policies"),
        "all": OptDef(flag="-A", is_flag=True, help="All enumeration (default)"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".json"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``enum4linux-ng -A {target} -oJ {output_file}``."""
        output_file = self._make_output_path()

        has_enum_flag = any(
            kwargs.get(k) for k in ("users", "shares", "groups", "policies", "all")
        )

        parts: list[str] = [self.cmd]
        if not has_enum_flag:
            parts.append("-A")

        parts.extend(self._build_opt_parts(kwargs))

        parts.extend(["-oJ", str(output_file).removesuffix(".json")])
        parts.append(self._q(target))

        return " ".join(parts), output_file

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[UserAccount | Tag]:
        results: list[UserAccount | Tag] = []

        data = self._read_json_output(stdout, output_file)
        if data is None:
            return results

        # Users
        users = data.get("users", {})
        for _rid, info in users.items():
            username = info.get("username", "") if isinstance(info, dict) else str(info)
            if username:
                results.append(
                    UserAccount(
                        username=username,
                        domain=info.get("domain", "") if isinstance(info, dict) else "",
                        source="enum4linux",
                    )
                )

        # Shares
        for share in data.get("shares", []):
            name = share.get("name", "") if isinstance(share, dict) else str(share)
            if name:
                results.append(Tag(name="share", value=name, category="ad"))

        # Groups
        for group in data.get("groups", []):
            name = group.get("groupname", "") if isinstance(group, dict) else str(group)
            if name:
                results.append(Tag(name="group", value=name, category="ad"))

        # OS info
        os_info = data.get("os_info", {})
        if isinstance(os_info, dict):
            os_str = os_info.get("OS", "")
            if os_str:
                results.append(Tag(name="os", value=os_str, category="ad"))

        return results
