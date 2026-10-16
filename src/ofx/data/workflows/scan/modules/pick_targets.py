"""Select fuzz targets, skipping WAF/CDN-protected hosts.

Fails closed: when the WAF/CDN filter is unavailable (or reported no usable
detection) the module refuses to fuzz instead of falling back to every target.
``force=true`` bypasses the filter explicitly.
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


def _read(path):
    if not path or not os.path.isfile(path):
        return []
    with open(path) as fh:
        return [line.strip() for line in fh if line.strip()]


def run(ctx):
    rd = _artifact_dir(ctx)
    src = str(ctx.inputs.get("target") or "")
    clean = str(ctx.inputs.get("clean_targets") or "")
    detection_available = (
        str(ctx.inputs.get("detection_available") or "").strip().lower() == "true"
    )
    force = str(ctx.inputs.get("force") or "false").strip().lower() == "true"
    out = os.path.join(rd, "fuzz_targets.txt")

    if force:
        targets = _read(src)
        if not detection_available:
            print("force=true — fuzzing all targets (WAF/CDN filter bypassed)")
    elif not detection_available:
        raise RuntimeError(
            "WAF/CDN detection unavailable, refusing to fuzz unverified targets. "
            "Install cdncheck/wafw00f, or pass force=true to fuzz anyway."
        )
    elif not os.path.isfile(clean):
        raise RuntimeError(
            f"WAF/CDN detection reported results but {clean!r} is missing"
        )
    else:
        targets = _read(clean)
        for skipped in _read(src):
            if skipped not in targets:
                print(f"skipped (WAF/CDN): {skipped}")

    with open(out, "w") as fh:
        if targets:
            fh.write("\n".join(targets) + "\n")
    print(f"fuzz list: {len(targets)} targets")
    ctx.add_outputs(fuzz_targets=out, target_count=len(targets))
