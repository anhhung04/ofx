"""Parse nmap_scan.xml into a human-readable host/port inventory."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET


def run(ctx):
    xml_file = os.path.join(ctx.env.get("OFX_RUN_DIR", ""), "nmap_scan.xml")
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        hosts = []
        for host in root.findall("host"):
            addr = host.find("address")
            if addr is not None:
                ip = addr.get("addr", "")
                ports = []
                for port in host.findall("ports/port"):
                    pid = port.get("portid", "")
                    svc = port.find("service")
                    svc_name = svc.get("name", "") if svc is not None else ""
                    ports.append(f"{pid}/{svc_name}")
                hosts.append(f"{ip}: {', '.join(ports)}")
        print(f"Found {len(hosts)} hosts with open ports")
        for h in hosts:
            print(h)
    except FileNotFoundError:
        print("No nmap results found")
