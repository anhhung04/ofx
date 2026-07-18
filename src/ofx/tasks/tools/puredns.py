"""puredns — fast DNS bruteforcing and resolution with massdns."""

from __future__ import annotations

from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Subdomain
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("puredns")
class PurednsTask(Task):
    name = "puredns"
    cmd = "puredns"
    description = "Fast DNS bruteforcing and resolution with massdns"
    category = "dns/brute"
    install_cmd = (
        "GOBIN=$TOOLS_BIN_DIR go install -v github.com/d3mondev/puredns/v2@latest"
    )
    output_types = [Subdomain]

    opts = {
        "resolvers": OptDef(flag="-r", type=str, help="Resolvers file"),
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "rate_limit": OptDef(
            flag="--rate-limit", type=int, help="Rate limit per second"
        ),
        "wildcard_tests": OptDef(
            flag="--wildcard-tests", type=int, help="Wildcard detection tests"
        ),
        "wildcard_batch": OptDef(
            flag="--wildcard-batch", type=int, help="Wildcard batch size"
        ),
        "trusted_resolvers": OptDef(
            flag="--resolvers-trusted", type=str, help="Trusted resolvers file"
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = "-w"
    silent_flag = "--quiet"
    extra_flags = ["resolve"]

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: object) -> tuple[str, Path | None]:
        """Build: puredns resolve [flags] <input_file> -w <output_file>."""
        parts = [self.cmd, *self.extra_flags]

        if self.json_flag:
            parts.append(self.json_flag)
        if self.silent_flag:
            parts.append(self.silent_flag)

        parts.extend(self._build_opt_parts(kwargs))

        output_file: Path | None = None
        if self.output_flag:
            output_file = self._make_output_path()
            parts.extend([self.output_flag, str(output_file)])

        if target:
            parts.append(self._q(target))

        return " ".join(parts), output_file

    def parse_line(self, line: str) -> list[Subdomain]:
        host = line.strip()
        if not host or host.startswith("#"):
            return []

        domain = ".".join(host.rsplit(".", 2)[-2:]) if "." in host else host
        return [Subdomain(host=host, domain=domain)]
