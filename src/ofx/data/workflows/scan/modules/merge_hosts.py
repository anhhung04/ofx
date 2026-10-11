"""Merge fping and naabu live-host lists into one de-duplicated file.

Raises when neither producer left an artifact: an empty host list must mean
"no live hosts", never "the discovery steps never ran".
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


def run(ctx):
    rd = _artifact_dir(ctx)
    files = ["live_hosts.txt", "live_hosts_naabu.txt"]
    seen = set()
    missing = []
    for name in files:
        try:
            with open(os.path.join(rd, name)) as fh:
                seen.update(line.strip() for line in fh if line.strip())
        except FileNotFoundError:
            missing.append(name)
    if len(missing) == len(files):
        raise RuntimeError(
            f"no host discovery results: none of {', '.join(files)} were produced"
        )

    out = os.path.join(rd, "all_live_hosts.txt")
    hosts = sorted(seen)
    with open(out, "w") as fh:
        if hosts:
            fh.write("\n".join(hosts) + "\n")
    print(f"Found {len(hosts)} live hosts")
    ctx.add_outputs(host_count=len(hosts), host_file=out)
