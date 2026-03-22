"""assetfinder — simple subdomain finder using various sources."""

from __future__ import annotations

from pathlib import Path

from ofx.tasks.base import Task
from ofx.tasks.output_types import Subdomain
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("assetfinder")
class AssetfinderTask(Task):
    name = "assetfinder"
    cmd = "assetfinder"
    description = "Simple subdomain finder using various sources"
    category = "dns/recon"
    install_cmd = (
        "GOBIN=~/Tools/bin go install -v github.com/tomnomnom/assetfinder@latest"
    )
    output_types = [Subdomain]

    opts = {}

    input_flag = None  # positional, last argument
    file_flag = None  # reads stdin
    output_flag = None  # stdout only
    extra_flags = ["--subs-only"]

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
