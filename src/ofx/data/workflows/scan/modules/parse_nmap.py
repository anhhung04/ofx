"""Parse the nmap XML output into a host/port inventory.

Publishes the parsed inventory so callers do not have to re-parse the XML, and
raises when nmap left no usable output (service detection must not silently
"succeed" on nothing).
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET


def _artifact_dir(ctx):
    """Return the directory holding this workflow's artifacts."""
    explicit = str(ctx.inputs.get("output_dir") or "").strip()
    run_dir = (
        explicit
        or os.environ.get("OFX_RUN_DIR")
        or str(ctx.env.get("OFX_RUN_DIR") or "")
    )
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot locate run artifacts")
    return run_dir


def run(ctx):
    rd = _artifact_dir(ctx)
    xml_file = os.path.join(rd, "nmap_scan.xml")
    try:
        root = ET.parse(xml_file).getroot()
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"nmap produced no XML output ({xml_file} is missing); "
            "service detection failed"
        ) from exc
    except ET.ParseError as exc:
        raise RuntimeError(f"nmap output {xml_file} is not valid XML: {exc}") from exc

    hosts = []
    for host in root.findall("host"):
        addr = host.find("address")
        if addr is None:
            continue
        ports = []
        for port in host.findall("ports/port"):
            port_id = port.get("portid", "")
            svc = port.find("service")
            svc_name = svc.get("name", "") if svc is not None else ""
            ports.append(f"{port_id}/{svc_name}")
        hosts.append(f"{addr.get('addr', '')}: {', '.join(ports)}")

    inventory = "\n".join(hosts)
    inventory_file = os.path.join(rd, "nmap_inventory.txt")
    with open(inventory_file, "w") as fh:
        if inventory:
            fh.write(inventory + "\n")
    print(f"Found {len(hosts)} hosts with open ports")
    for line in hosts:
        print(line)
    ctx.add_outputs(
        nmap_file=xml_file,
        host_count=len(hosts),
        inventory=inventory,
        inventory_file=inventory_file,
    )
