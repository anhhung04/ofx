"""Checksum the loot archive produced by the compress job."""

import hashlib
import os


def _run_dir(ctx) -> str:
    run_dir = os.environ.get("OFX_RUN_DIR") or str(ctx.env.get("OFX_RUN_DIR") or "")
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot locate the loot archive")
    return run_dir


def run(ctx):
    f = str(ctx.inputs.get("archive") or "") or os.path.join(
        _run_dir(ctx), "loot.tar.gz"
    )
    if not os.path.isfile(f):
        raise FileNotFoundError(
            f"Loot archive not found: {f} (compression step did not produce it)"
        )
    sha = hashlib.sha256()
    with open(f, "rb") as fh:
        while True:
            chunk = fh.read(8192)
            if not chunk:
                break
            sha.update(chunk)
    size = os.path.getsize(f)
    print(f"Archive: {f}")
    print(f"Size: {size} bytes")
    print(f"SHA256: {sha.hexdigest()}")
    ctx.add_outputs(
        archive=f,
        archive_name=os.path.basename(f),
        size=size,
        sha256=sha.hexdigest(),
    )
