"""Turn naabu output (``host:port`` lines) into nmap host/port arguments.

``nmap -iL`` expects hosts, but naabu writes one ``host:port`` pair per line;
feeding that file straight to nmap makes nmap treat ``host:port`` as a host.
This module splits the results into a host file and a port list, and fails
closed when naabu left no usable output.
"""

from __future__ import annotations

import os


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


def _split_endpoint(value):
    """Split ``host:port`` (or ``[v6]:port``) into (host, port)."""
    text = value.strip()
    if not text:
        return "", ""
    if text.startswith("["):
        host, _, rest = text[1:].partition("]")
        return host.strip(), rest.lstrip(":").strip()
    host, sep, port = text.rpartition(":")
    if not sep or not port:
        return text, ""
    return host.strip(), port.strip()


def run(ctx):
    rd = _artifact_dir(ctx)
    source = str(ctx.inputs.get("naabu_file") or os.path.join(rd, "open_ports_naabu.txt"))
    if not os.path.isfile(source):
        raise RuntimeError(
            f"naabu left no results ({source} is missing); service detection "
            "cannot continue"
        )
    with open(source) as fh:
        lines = [line.strip() for line in fh if line.strip()]

    hosts, ports = [], []
    for line in lines:
        host, port = _split_endpoint(line)
        if host and host not in hosts:
            hosts.append(host)
        if port and port.isdigit() and port not in ports:
            ports.append(port)
    if not hosts or not ports:
        raise RuntimeError(
            f"naabu reported no open ports ({source}); service detection cannot "
            "continue"
        )

    hosts = sorted(hosts)
    ports.sort(key=int)
    host_file = os.path.join(rd, "nmap_hosts.txt")
    with open(host_file, "w") as fh:
        fh.write("\n".join(hosts) + "\n")
    port_list = ",".join(ports)
    print(f"naabu found {len(ports)} open ports across {len(hosts)} hosts")
    ctx.add_outputs(
        nmap_hosts=host_file,
        host_count=len(hosts),
        open_ports=port_list,
        port_count=len(ports),
    )
