"""brutus — automated credential brute-forcing for discovered services."""

from __future__ import annotations

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("brutus")
class BrutusTask(Task):
    name = "brutus"
    cmd = "brutus"
    description = "Automated credential brute-forcing for discovered services"
    category = "brute/credential"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/praetorian-inc/brutus/cmd/brutus@latest"
    output_types = [UserAccount]

    opts = {
        "protocol": OptDef(flag="--protocol", type=str, help="Target protocol (ssh,mysql,rdp,etc)"),
        "username": OptDef(flag="-u", type=str, help="Username or comma-separated list"),
        "password": OptDef(flag="-p", type=str, help="Password or comma-separated list"),
        "user_file": OptDef(flag="-U", type=str, help="Username wordlist file"),
        "pass_file": OptDef(flag="-P", type=str, help="Password wordlist file"),
        "key": OptDef(flag="-k", type=str, help="SSH private key file"),
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "badkeys_only": OptDef(flag="--badkeys-only", is_flag=True, help="Test only embedded SSH bad keys"),
        "no_badkeys": OptDef(flag="--no-badkeys", is_flag=True, help="Disable embedded bad key testing"),
        "verbose": OptDef(flag="-v", is_flag=True, help="Verbose output"),
    }

    input_flag = "--target"
    file_flag = None
    output_flag = "-o"
    json_flag = "--json"

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[UserAccount]:
        data = self._parse_json_line(line)
        if data is None:
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

