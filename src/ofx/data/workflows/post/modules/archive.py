"""Create a tar.gz archive of loot, replacing the brittle ``tar -C <path> .`` shell form.

Accepts a directory or a list of files, uses argument vectors (no shell
quoting problems with paths that contain spaces), and publishes the resulting
archive path for the checksum/exfiltration stages.
"""

import os
import subprocess
import tarfile


def _run_dir(ctx) -> str:
    run_dir = os.environ.get("OFX_RUN_DIR") or str(ctx.env.get("OFX_RUN_DIR") or "")
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write the loot archive")
    return run_dir


def _targets(raw: str) -> list[str]:
    separator = "," if "," in raw else ("\n" if "\n" in raw else " ")
    return [part.strip() for part in raw.split(separator) if part.strip()]


def run(ctx):
    target = str(ctx.inputs.get("target") or "").strip()
    if not target:
        raise ValueError("'target' (loot directory or file list) is required")

    run_dir = _run_dir(ctx)
    archive = os.path.join(run_dir, "loot.tar.gz")

    entries = _targets(target)
    missing = [entry for entry in entries if not os.path.exists(entry)]
    if missing:
        raise FileNotFoundError(f"Loot path(s) not found: {', '.join(missing)}")

    try:
        with tarfile.open(archive, "w:gz") as tar:
            for entry in entries:
                tar.add(entry, arcname=os.path.basename(os.path.normpath(entry)))
    except (tarfile.TarError, OSError):
        # Fall back to the system tar when Python's tarfile cannot handle a
        # path (e.g. special files or unsupported metadata).
        if os.path.exists(archive):
            os.remove(archive)
        argv = ["tar", "-czf", archive]
        for entry in entries:
            argv += ["-C", os.path.dirname(os.path.abspath(entry)), os.path.basename(entry)]
        subprocess.run(argv, check=True)  # noqa: S603

    if not os.path.isfile(archive):
        raise RuntimeError(f"Archive was not created: {archive}")

    size = os.path.getsize(archive)
    print(f"[+] Archive: {archive} ({size} bytes, {len(entries)} path(s))")
    ctx.add_outputs(
        archive=archive,
        archive_name=os.path.basename(archive),
        size=size,
        paths=entries,
    )
