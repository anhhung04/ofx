"""gau — fetch known URLs from AlienVault, Wayback Machine, and Common Crawl."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Subdomain, Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("gau")
class GauTask(Task):
    name = "gau"
    cmd = "gau"
    description = "Fetch known URLs from AlienVault OTX, Wayback Machine, and Common Crawl"
    category = "url/recon"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/lc/gau/v2/cmd/gau@latest"
    output_types = [Url, Subdomain]

    opts = {
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "providers": OptDef(
            flag="--providers", type=str, help="Comma-separated providers to use"
        ),
        "blacklist": OptDef(
            flag="--blacklist", type=str, help="Comma-separated extensions to skip"
        ),
        "from_date": OptDef(
            flag="--from", type=str, help="Date range start (YYYYMM)"
        ),
        "to_date": OptDef(flag="--to", type=str, help="Date range end (YYYYMM)"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["--json"]

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Url | Subdomain]:
        line = line.strip()
        if not line:
            return []

        results: list[Url | Subdomain] = []

        if line.startswith("{"):
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                return []

            url = data.get("url", "")
            if not url:
                return []

            status_code = self._safe_int(data.get("status", 0))
            results.append(Url(url=url, status_code=status_code))

            try:
                host = urlparse(url).hostname or ""
            except ValueError:
                host = ""

            if host and "." in host:
                domain = ".".join(host.rsplit(".", 2)[-2:])
                results.append(Subdomain(host=host, domain=domain))
        else:
            # Plain URL fallback (non-JSON mode)
            if line.startswith("http://") or line.startswith("https://"):
                results.append(Url(url=line))

        return results

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Url | Subdomain]:
        results: list[Url | Subdomain] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results
