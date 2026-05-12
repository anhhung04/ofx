"""assetfinder — simple subdomain finder using various sources."""

from __future__ import annotations

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
        "GOBIN=$TOOLS_BIN_DIR go install -v github.com/tomnomnom/assetfinder@latest"
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
