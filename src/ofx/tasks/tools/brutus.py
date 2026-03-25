"""brutus — automated credential brute-forcing for discovered services."""

from __future__ import annotations

import json
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("brutus")
class BrutusTask(Task):
    name = "brutus"
    cmd = "brutus"
    description = "Automated credential brute-forcing for discovered services"
    category = "brute/credential"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/brutus-project/cmd/brutus@latest"
    output_types = [UserAccount]

    opts = {
        "threads": OptDef(flag="-c", type=int, help="Concurrency / threads"),
        "timeout": OptDef(flag="-timeout", type=int, help="Timeout per attempt in seconds"),
        "retries": OptDef(flag="-retries", type=int, help="Number of retries"),
        "rate": OptDef(flag="-rate", type=int, help="Max rate (attempts/sec)"),
        "passwords": OptDef(flag="-passwords", type=str, help="Custom password wordlist file"),
        "usernames": OptDef(flag="-usernames", type=str, help="Custom username wordlist file"),
        "stop_on_success": OptDef(flag="-stop-on-success", is_flag=True, help="Stop on first valid credential per host"),
        "service": OptDef(flag="-service", type=str, help="Target specific service (ssh,ftp,mysql,etc)"),
    }

    input_flag = "-host"
    file_flag = "-list"
    output_flag = "-o"
    extra_flags = ["--json"]

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[UserAccount]:
        line = line.strip()
        if not line or not line.startswith("{"):
            return []
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return []

        username = data.get("username", data.get("login", ""))
        password = data.get("password", data.get("pass", ""))

        if not username:
            return []

        host = data.get("host", data.get("ip", ""))
        port = data.get("port", 0)
        service = data.get("service", data.get("protocol", ""))

        return [
            UserAccount(
                username=username,
                password=password,
                host=f"{host}:{port}" if port else host,
                source=f"brutus/{service}" if service else "brutus",
                extra_data={
                    k: v
                    for k, v in {
                        "service": service,
                        "port": port,
                        "banner": data.get("banner", ""),
                    }.items()
                    if v
                },
            )
        ]

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[UserAccount]:
        results: list[UserAccount] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results
