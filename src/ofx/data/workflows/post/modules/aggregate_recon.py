"""Aggregate privilege-escalation enumeration results and fail when empty.

Each enumerator writes its output into ``OFX_RUN_DIR``; this module checks that
at least one requested enumerator produced a non-empty artifact, so a stage
cannot report success when nothing was actually enumerated.
"""

import os

# enumerator key -> output file name (relative to OFX_RUN_DIR)
LINUX_ENUMERATORS = {
    "linpeas": "linpeas_results.txt",
    "linux-smart": "lse_results.txt",
}
WINDOWS_ENUMERATORS = {
    "winpeas": "winpeas_results.txt",
}


def _run_dir(ctx) -> str:
    run_dir = os.environ.get("OFX_RUN_DIR") or str(ctx.env.get("OFX_RUN_DIR") or "")
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot verify enumeration output")
    return run_dir


def _size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def run(ctx):
    os_type = str(ctx.inputs.get("os_type") or "linux").strip().lower()
    if os_type == "windows":
        enumerators = WINDOWS_ENUMERATORS
    elif os_type == "linux":
        enumerators = LINUX_ENUMERATORS
    else:
        raise ValueError(f"Unsupported os_type: '{os_type}' (expected linux or windows)")

    run_dir = _run_dir(ctx)
    results: dict[str, int] = {}
    for key, filename in enumerators.items():
        results[key] = _size(os.path.join(run_dir, filename))

    produced = [key for key, size in results.items() if size > 0]
    missing = [key for key, size in results.items() if size == 0]

    print(f"[+] Privilege escalation enumeration ({os_type}):")
    for key, size in results.items():
        state = f"{size} bytes" if size else "no output"
        print(f"    {key}: {state}")

    ctx.add_outputs(
        os_type=os_type,
        enumerators=list(results),
        produced=produced,
        missing=missing,
        artifact_sizes=results,
    )

    if not produced:
        raise RuntimeError(
            f"No {os_type} privilege-escalation enumerator produced a valid "
            f"artifact in {run_dir}; checked: {', '.join(enumerators)}"
        )
