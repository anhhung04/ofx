"""Checksum the loot archive produced by the compress job."""

import hashlib
import os


def run(ctx):
    f = os.path.join(os.environ["OFX_RUN_DIR"], "loot.tar.gz")
    if os.path.exists(f):
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
        ctx.add_outputs(archive=f, size=size, sha256=sha.hexdigest())
    else:
        print("Compression failed")
