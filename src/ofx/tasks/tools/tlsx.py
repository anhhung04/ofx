"""tlsx — TLS/SSL certificate analysis and subdomain discovery."""

from __future__ import annotations

import json

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Certificate, Subdomain
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("tlsx")
class TlsxTask(Task):
    name = "tlsx"
    cmd = "tlsx"
    description = "TLS/SSL certificate analysis and subdomain discovery"
    category = "cert/scan"
    install_cmd = (
        "GOBIN=~/Tools/bin go install -v github.com/projectdiscovery/tlsx/cmd/tlsx@latest"
    )
    output_types = [Certificate, Subdomain]

    opts = {
        "port": OptDef(flag="-p", type=str, help="Port(s) to scan (comma-separated)"),
        "san": OptDef(
            flag="-san", is_flag=True, help="Display Subject Alternative Names"
        ),
        "expired": OptDef(
            flag="-expired", is_flag=True, help="Show only expired certs"
        ),
        "self_signed": OptDef(
            flag="-self-signed", is_flag=True, help="Show only self-signed certs"
        ),
        "tls_version": OptDef(
            flag="-tls-version", type=str, help="Min TLS version (tls10, tls11, tls12, tls13)"
        ),
        "cipher": OptDef(flag="-cipher", is_flag=True, help="Display cipher info"),
        "hash": OptDef(
            flag="-hash", type=str, help="Hash type (md5, sha1, sha256)"
        ),
        "jarm": OptDef(flag="-jarm", is_flag=True, help="Compute JARM fingerprint"),
        "ja3": OptDef(flag="-ja3", is_flag=True, help="Show JA3 fingerprint"),
        "wildcard_cert": OptDef(
            flag="-wc", is_flag=True, help="Show wildcard certificates"
        ),
        "threads": OptDef(flag="-c", type=int, help="Number of concurrent threads"),
        "timeout": OptDef(flag="-timeout", type=int, help="Timeout in seconds"),
    }

    input_flag = "-u"
    file_flag = "-l"
    output_flag = "-o"
    json_flag = "-json"
    silent_flag = "-silent"

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Certificate | Subdomain]:
        line = line.strip()
        if not line or not line.startswith("{"):
            return []
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return []

        host = data.get("host", data.get("input", ""))
        if not host:
            return []

        results: list[Certificate | Subdomain] = []

        subject_cn = data.get("subject_cn", "")
        subject_an = data.get("subject_an", []) or []
        not_before = data.get("not_before", "")
        not_after = data.get("not_after", "")
        issuer_cn = data.get("issuer_cn", "")
        fingerprint = data.get("fingerprint_hash", {}).get("sha256", "")

        results.append(
            Certificate(
                host=host,
                subject_cn=subject_cn,
                subject_an=subject_an,
                not_before=not_before,
                not_after=not_after,
                fingerprint_sha256=fingerprint,
                extra_data={
                    "issuer_cn": issuer_cn,
                    "tls_version": data.get("tls_version", ""),
                    "cipher": data.get("cipher", ""),
                    "serial": data.get("serial", ""),
                },
            )
        )

        # Extract subdomains from SANs
        seen: set[str] = set()
        for san in subject_an:
            san = san.lstrip("*.")
            if san and san not in seen and "." in san:
                seen.add(san)
                domain = ".".join(san.rsplit(".", 2)[-2:])
                results.append(Subdomain(host=san, domain=domain, sources=["tlsx"]))

        # Also extract subdomain from CN if it looks like a hostname
        if subject_cn and "." in subject_cn and subject_cn not in seen:
            cn_clean = subject_cn.lstrip("*.")
            if cn_clean:
                domain = ".".join(cn_clean.rsplit(".", 2)[-2:])
                results.append(
                    Subdomain(host=cn_clean, domain=domain, sources=["tlsx"])
                )

        return results

