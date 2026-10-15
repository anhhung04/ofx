"""Build the list of web-facing targets for a given target type."""

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


def run(ctx):
    rd = _artifact_dir(ctx)
    target_type = str(ctx.inputs.get("target_type") or "")
    host_file = str(ctx.inputs.get("host_file") or "")
    candidates = {
        "domain": [
            os.path.join(rd, "all_subdomains.txt"),
            os.path.join(rd, "targets_domain.txt"),
        ],
        "subdomain": [os.path.join(rd, "targets_subdomain.txt")],
        "cidr": [host_file, os.path.join(rd, "targets_cidr.txt")],
        "ip": [os.path.join(rd, "targets_ip.txt")],
        "mixed": [
            os.path.join(rd, "all_subdomains.txt"),
            os.path.join(rd, "targets_domain.txt"),
            os.path.join(rd, "targets_subdomain.txt"),
            os.path.join(rd, "targets_ip.txt"),
        ],
    }
    sources = candidates.get(target_type, [os.path.join(rd, "targets_unknown.txt")])
    seen = set()
    for src in sources:
        if not src:
            continue
        try:
            with open(src) as fh:
                seen.update(line.strip() for line in fh if line.strip())
        except (FileNotFoundError, OSError):
            pass
    targets = sorted(seen)
    out = os.path.join(rd, "web_targets.txt")
    with open(out, "w") as fh:
        if targets:
            fh.write("\n".join(targets) + "\n")
    print(f"web targets: {len(targets)}")
    ctx.add_outputs(
        web_targets=out,
        web_target_count=len(targets),
        target_type=target_type,
    )
