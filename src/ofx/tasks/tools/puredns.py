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
        "GOBIN=~/Tools/bin go install -v github.com/d3mondev/puredns/v2@latest"
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

    # puredns resolve <file> — positional file, no flags
    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["resolve", "--quiet"]

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(
        self, target: str, **kwargs: object
    ) -> tuple[str, Path | None]:
        """Build: puredns resolve <input_file> [flags]."""
        parts = [self.cmd, *self.extra_flags]

        for key, val in kwargs.items():
            opt = self.opts.get(key)
            if opt and val is not None:
                if opt.is_flag:
                    if val:
                        parts.append(opt.flag)
                else:
                    parts.extend([opt.flag, str(val)])

        if target:
            parts.append(target)

        return " ".join(parts), None

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
