"""findomain — fast cross-platform subdomain enumerator."""

from __future__ import annotations

from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Subdomain
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("findomain")
class FindomainTask(Task):
    name = "findomain"
    cmd = "findomain"
    description = "Fast cross-platform subdomain enumerator"
    category = "dns/recon"
    install_cmd = (
        "mkdir -p ~/Tools/bin && curl -sL"
        " https://github.com/findomain/findomain/releases/latest/download/findomain-linux.zip"
        " -o /tmp/findomain.zip && unzip -o /tmp/findomain.zip -d ~/Tools/bin"
        " && chmod +x ~/Tools/bin/findomain && rm /tmp/findomain.zip"
    )
    output_types = [Subdomain]

    opts = {
        "threads": OptDef(flag="--threads", type=int, help="Number of threads"),
        "timeout": OptDef(flag="--timeout", type=int, help="Timeout in seconds"),
        "resolvers": OptDef(flag="-r", type=str, help="Path to resolvers file"),
    }

    input_flag = "-t"
    file_flag = "-f"
    output_flag = "-u"
    extra_flags = ["-q"]

    def _output_suffix(self) -> str:
        return ".txt"

    def parse_line(self, line: str) -> list[Subdomain]:
        host = line.strip()
        if not host or host.startswith("#"):
            return []

        domain = ".".join(host.rsplit(".", 2)[-2:]) if "." in host else host

        return [Subdomain(host=host, domain=domain)]

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Subdomain]:
        results: list[Subdomain] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results
