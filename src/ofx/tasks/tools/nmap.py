"""Nmap — network port scanner and service detector."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Confidence, Ip, Port, Severity, Vulnerability
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("nmap")
class NmapTask(Task):
    name = "nmap"
    cmd = "nmap"
    description = "Network port scanner and service detector"
    category = "port/scan"
    install_cmd = "apt install -y nmap"
    output_types = [Ip, Port, Vulnerability]

    opts = {
        "ports": OptDef(flag="-p", type=str, help="Port range to scan"),
        "ping_scan": OptDef(
            flag="-sn", is_flag=True, help="Ping scan only — no port scan"
        ),
        "version_detection": OptDef(
            flag="-sV", is_flag=True, help="Detect service versions"
        ),
        "tcp_syn": OptDef(flag="-sS", is_flag=True, help="TCP SYN stealth scan"),
        "os_detect": OptDef(flag="-O", is_flag=True, help="OS detection"),
        "scripts": OptDef(flag="--script", type=str, help="NSE scripts to run"),
        "timing": OptDef(flag="-T", type=int, help="Timing template (0-5)"),
        "top_ports": OptDef(
            flag="--top-ports", type=int, help="Scan N most common ports"
        ),
        "fragment": OptDef(
            flag="-f", is_flag=True, help="Fragment packets for evasion"
        ),
    }

    input_flag = None
    file_flag = "-iL"
    output_flag = "-oX"

    def _output_suffix(self) -> str:
        return ".xml"

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Ip | Port | Vulnerability]:
        results: list[Ip | Port | Vulnerability] = []

        xml_source = self._raw_output(
            stdout if "<nmaprun" in stdout else "",
            output_file,
        )

        if not xml_source:
            return results

        try:
            root = ET.fromstring(xml_source)
        except ET.ParseError:
            return results

        for host_el in root.findall("host"):
            addr_el = host_el.find("address")
            ip = addr_el.get("addr", "") if addr_el is not None else ""

            hostname = ""
            hostnames_el = host_el.find("hostnames")
            if hostnames_el is not None:
                hn_el = hostnames_el.find("hostname")
                if hn_el is not None:
                    hostname = hn_el.get("name", "")

            status_el = host_el.find("status")
            host_state = status_el.get("state", "") if status_el is not None else ""

            ports_el = host_el.find("ports")
            if ports_el is None:
                if host_state == "up":
                    results.append(Ip(ip=ip, host=hostname, alive=True))
                continue

            for port_el in ports_el.findall("port"):
                portid = self._safe_int(port_el.get("portid"))
                protocol = port_el.get("protocol", "tcp")

                state_el = port_el.find("state")
                state = (
                    state_el.get("state", "unknown")
                    if state_el is not None
                    else "unknown"
                )
                if state not in ("open", "open|filtered"):
                    continue

                service_el = port_el.find("service")
                service_name = ""
                cpes: list[str] = []
                if service_el is not None:
                    parts = [service_el.get("name", "")]
                    product = service_el.get("product", "")
                    version = service_el.get("version", "")
                    if product:
                        parts.append(product)
                    if version:
                        parts.append(version)
                    service_name = "/".join(p for p in parts if p)
                    cpes = [
                        cpe_el.text
                        for cpe_el in service_el.findall("cpe")
                        if cpe_el.text
                    ]

                results.append(
                    Port(
                        port=portid,
                        ip=ip,
                        host=hostname,
                        state=state,
                        protocol=protocol,
                        service_name=service_name,
                        cpes=cpes,
                    )
                )

                for script_el in port_el.findall("script"):
                    script_id = script_el.get("id", "")
                    script_output = script_el.get("output", "")
                    if (
                        "VULNERABLE" in script_output.upper()
                        or "CVE-" in script_output.upper()
                    ):
                        results.append(
                            Vulnerability(
                                name=script_id,
                                matched_at=f"{ip}:{portid}",
                                provider="nmap",
                                severity=Severity.MEDIUM,
                                confidence=Confidence.MEDIUM,
                                description=script_output[:500],
                            )
                        )

        return results
