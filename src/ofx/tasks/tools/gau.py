"""gau — fetch known URLs from AlienVault, Wayback Machine, and Common Crawl."""

from __future__ import annotations

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Subdomain, Url
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("gau")
class GauTask(Task):
    name = "gau"
    cmd = "gau"
    description = (
        "Fetch known URLs from AlienVault OTX, Wayback Machine, and Common Crawl"
    )
    category = "url/recon"
    install_cmd = "GOBIN=$TOOLS_BIN_DIR go install -v github.com/lc/gau/v2/cmd/gau@latest"
    output_types = [Url, Subdomain]

    opts = {
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "providers": OptDef(
            flag="--providers", type=str, help="Comma-separated providers to use"
        ),
        "blacklist": OptDef(
            flag="--blacklist", type=str, help="Comma-separated extensions to skip"
        ),
        "from_date": OptDef(flag="--from", type=str, help="Date range start (YYYYMM)"),
        "to_date": OptDef(flag="--to", type=str, help="Date range end (YYYYMM)"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    json_flag = "--json"

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Url | Subdomain]:
        line = line.strip()
        if not line:
            return []

        results: list[Url | Subdomain] = []

        if line.startswith("{"):
            data = self._parse_json_line(line)
            if data is None:
                return []

            url = data.get("url", "")
            if not url:
                return []

            status_code = self._safe_int(data.get("status", 0))
            results.append(Url(url=url, status_code=status_code))

            host = self._url_host(url)
            if host and "." in host:
                domain = ".".join(host.rsplit(".", 2)[-2:])
                results.append(Subdomain(host=host, domain=domain))
        else:
            if line.startswith("http://") or line.startswith("https://"):
                results.append(Url(url=line))

        return results
