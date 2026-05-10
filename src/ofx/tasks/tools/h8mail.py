"""h8mail — email OSINT and password breach hunting tool."""

from __future__ import annotations

from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("h8mail")
class H8mailTask(Task):
    name = "h8mail"
    cmd = "h8mail"
    description = "Email OSINT and password breach hunting tool"
    category = "user/recon/email"
    install_cmd = "uv tool install h8mail"
    output_types = [UserAccount]

    opts = {
        "config": OptDef(flag="-c", type=str, help="Config file with API keys"),
        "local_breach": OptDef(
            flag="-lb", type=str, help="Local breach file to search"
        ),
        "chase_limit": OptDef(
            flag="--chase-limit", type=int, help="Max results to chase"
        ),
        "skip_defaults": OptDef(
            flag="-sk", is_flag=True, help="Skip default API queries"
        ),
    }

    input_flag = "-t"
    file_flag = None
    output_flag = "--json"
    extra_flags = []

    def _output_suffix(self) -> str:
        return ".json"

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[UserAccount]:
        data = self._read_json_output(stdout, output_file)
        if data is None:
            return []

        results: list[UserAccount] = []
        for target in data.get("targets", []):
            if not isinstance(target, dict):
                continue
            email = target.get("target", "")
            for entry in target.get("data", []):
                if not isinstance(entry, dict):
                    continue
                breach = entry.get("breach", "")
                password = entry.get("password", "")
                results.append(
                    UserAccount(
                        username=email,
                        password=password,
                        source=breach or "h8mail",
                        extra_data={"breach": breach},
                    )
                )

        return results
