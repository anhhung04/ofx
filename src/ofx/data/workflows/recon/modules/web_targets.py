"""Build the list of web-facing targets for a given target type."""

from __future__ import annotations

import os


def run(ctx):
    rd = os.environ["OFX_RUN_DIR"]
    target_type = ctx.inputs.get("target_type", "")
    host_file = ctx.inputs.get("host_file", "")
    seen = set()
    candidates = {
        "domain": [os.path.join(rd, "all_subdomains.txt"), os.path.join(rd, "targets_domain.txt")],
        "subdomain": [os.path.join(rd, "targets_subdomain.txt")],
        "cidr": [host_file, os.path.join(rd, "targets_cidr.txt")],
        "ip": [os.path.join(rd, "targets_ip.txt")],
        "mixed": [os.path.join(rd, "all_subdomains.txt"), os.path.join(rd, "targets_domain.txt"), os.path.join(rd, "targets_subdomain.txt"), os.path.join(rd, "targets_ip.txt")],
    }
    for src in candidates.get(target_type, [os.path.join(rd, "targets_unknown.txt")]):
        try:
            with open(src) as fh:
                seen.update(line.strip() for line in fh if line.strip())
        except (FileNotFoundError, OSError):
            pass
    out = os.path.join(rd, "web_targets.txt")
    with open(out, "w") as fh:
        fh.write("\n".join(sorted(seen)))
    print(f"web targets: {len(seen)}")
    ctx.add_outputs(web_targets=out)
