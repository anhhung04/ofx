"""cdncheck — identify CDN, WAF, and cloud providers for IPs and domains."""

from __future__ import annotations

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Ip, Tag
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("cdncheck")
class CdncheckTask(Task):
    name = "cdncheck"
    cmd = "cdncheck"
    description = "Identify CDN/WAF/cloud providers for IPs and domains"
    category = "recon/cdn"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/projectdiscovery/cdncheck/cmd/cdncheck@latest"
    output_types = [Tag, Ip]

    opts = {
        "resolver": OptDef(flag="-r", type=str, help="DNS resolver to use"),
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "exclude": OptDef(
            flag="-exclude", is_flag=True, help="Exclude CDN/WAF IPs from output"
        ),
        "match_cdn": OptDef(
            flag="-match-cdn", type=str, help="Match specific CDN provider"
        ),
        "match_waf": OptDef(
            flag="-match-waf", type=str, help="Match specific WAF provider"
        ),
        "match_cloud": OptDef(
            flag="-match-cloud", type=str, help="Match specific cloud provider"
        ),
    }

    input_flag = "-i"  # single input
    file_flag = "-list"
    output_flag = "-o"
    json_flag = "-json"
    silent_flag = "-silent"

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Tag | Ip]:
        data = self._parse_json_line(line)
        if data is None:
            return []

        ip = data.get("ip", data.get("input", ""))
        if not ip:
            return []

        results: list[Tag | Ip] = []
        results.append(Ip(ip=ip, host=ip))

        cdn_name = data.get("cdn_name", "")
        if cdn_name:
            results.append(Tag(name=cdn_name, value=cdn_name, match=ip, category="cdn"))

        waf_name = data.get("waf_name", "")
        if waf_name:
            results.append(Tag(name=waf_name, value=waf_name, match=ip, category="waf"))

        cloud_name = data.get("cloud_name", "")
        if cloud_name:
            results.append(
                Tag(name=cloud_name, value=cloud_name, match=ip, category="cloud")
            )

        # Include type tag (cdn/waf/cloud/none)
        item_type = data.get("type", "")
        if item_type and item_type != "none":
            results.append(
                Tag(name=item_type, value=item_type, match=ip, category="provider-type")
            )

        return results
