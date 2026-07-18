"""dnsx — fast DNS toolkit with retries and multiple resolvers."""

from __future__ import annotations

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Ip, Record, Subdomain
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("dnsx")
class DnsxTask(Task):
    name = "dnsx"
    cmd = "dnsx"
    description = "Fast and multi-purpose DNS toolkit"
    category = "dns/resolve"
    install_cmd = "GOBIN=$TOOLS_BIN_DIR go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest"
    output_types = [Subdomain, Ip, Record]

    opts = {
        "a": OptDef(flag="-a", is_flag=True, help="Query A records"),
        "aaaa": OptDef(flag="-aaaa", is_flag=True, help="Query AAAA records"),
        "cname": OptDef(flag="-cname", is_flag=True, help="Query CNAME records"),
        "mx": OptDef(flag="-mx", is_flag=True, help="Query MX records"),
        "ns": OptDef(flag="-ns", is_flag=True, help="Query NS records"),
        "txt": OptDef(flag="-txt", is_flag=True, help="Query TXT records"),
        "soa": OptDef(flag="-soa", is_flag=True, help="Query SOA records"),
        "ptr": OptDef(flag="-ptr", is_flag=True, help="Query PTR records"),
        "any": OptDef(flag="-any", is_flag=True, help="Query ANY records"),
        "resp": OptDef(flag="-resp", is_flag=True, help="Show DNS response"),
        "resp_only": OptDef(
            flag="-resp-only", is_flag=True, help="Show only response values"
        ),
        "resolver": OptDef(flag="-r", type=str, help="Resolver list (comma-separated)"),
        "resolver_file": OptDef(flag="-rL", type=str, help="File containing resolvers"),
        "threads": OptDef(flag="-t", type=int, help="Number of concurrent threads"),
        "rate_limit": OptDef(
            flag="-rate-limit", type=int, help="Max DNS queries per second"
        ),
        "retries": OptDef(flag="-retry", type=int, help="Number of retries"),
        "wildcard_domain": OptDef(
            flag="-wd", type=str, help="Domain for wildcard filtering"
        ),
        "trace": OptDef(flag="-trace", is_flag=True, help="Perform DNS trace"),
        "wordlist": OptDef(flag="-w", type=str, help="Wordlist for DNS bruteforcing"),
    }

    input_flag = None
    file_flag = "-l"
    output_flag = "-o"
    json_flag = "-json"
    silent_flag = "-silent"

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Subdomain | Ip | Record]:
        data = self._parse_json_line(line)
        if data is None:
            return []

        host = data.get("host", "")
        if not host:
            return []

        domain = ".".join(host.rsplit(".", 2)[-2:]) if "." in host else host
        results: list[Subdomain | Ip | Record] = [Subdomain(host=host, domain=domain)]

        for a_record in data.get("a", []):
            results.append(Ip(ip=a_record, host=host))

        for aaaa_record in data.get("aaaa", []):
            results.append(Ip(ip=aaaa_record, host=host))

        for cname in data.get("cname", []):
            results.append(Record(name=cname, type="CNAME", host=host))

        for mx in data.get("mx", []):
            results.append(Record(name=mx, type="MX", host=host))

        for ns in data.get("ns", []):
            results.append(Record(name=ns, type="NS", host=host))

        for txt in data.get("txt", []):
            results.append(Record(name=txt, type="TXT", host=host))

        return results
