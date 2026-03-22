"""subfinder — fast passive subdomain enumeration."""

from __future__ import annotations

from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Subdomain
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("subfinder")
class SubfinderTask(Task):
    name = "subfinder"
    cmd = "subfinder"
    description = "Fast passive subdomain enumeration tool"
    category = "dns/recon"
    install_cmd = (
        "go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"
    )
    output_types = [Subdomain]

    opts = {
        "sources": OptDef(flag="-sources", type=str, help="Comma-separated sources"),
        "recursive": OptDef(
            flag="-recursive", is_flag=True, help="Use recursive enumeration"
        ),
        "all": OptDef(flag="-all", is_flag=True, help="Use all sources"),
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "timeout": OptDef(flag="-timeout", type=int, help="Timeout in seconds"),
        "rate_limit": OptDef(
            flag="-rate-limit", type=int, help="Max requests per second"
        ),
        "max_time": OptDef(
            flag="-max-time", type=int, help="Max enumeration time in minutes"
        ),
        "exclude_sources": OptDef(
            flag="-es", type=str, help="Exclude comma-separated sources"
        ),
    }

    input_flag = "-d"
    file_flag = "-dL"
    output_flag = "-o"

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs):
        parts = [self.cmd, "-silent"]

        for key, value in kwargs.items():
            opt = self.opts.get(key)
            if opt is None:
                continue
            if opt.is_flag:
                if value:
                    parts.append(opt.flag)
            elif value is not None:
                parts.extend([opt.flag, str(value)])

        output_file = None
        if self.output_flag:
            import tempfile

            output_file = Path(
                tempfile.mkstemp(prefix=".ofx_task_subfinder_", suffix=".txt")[1]
            )
            parts.extend([self.output_flag, str(output_file)])

        if self.input_flag:
            parts.extend([self.input_flag, target])
        else:
            parts.append(target)

        return " ".join(parts), output_file

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Subdomain]:
        results: list[Subdomain] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = output_file.read_text().strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            host = line.strip()
            if not host or host.startswith("#"):
                continue

            domain = ".".join(host.rsplit(".", 2)[-2:]) if "." in host else host

            results.append(Subdomain(host=host, domain=domain))

        return results
