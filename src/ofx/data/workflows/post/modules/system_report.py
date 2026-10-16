"""Write a run-scoped situational-awareness report from captured step output.

The enumeration steps are best-effort probe chains whose results used to live
only in unstructured stdout. This module persists the captured output as a
report file and publishes the section inventory, failing when nothing was
captured so an empty recon stage can never report success.
"""

import os
from datetime import UTC, datetime


def _run_dir(ctx) -> str:
    run_dir = os.environ.get("OFX_RUN_DIR") or str(ctx.env.get("OFX_RUN_DIR") or "")
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write the recon report")
    return run_dir


def run(ctx):
    os_type = str(ctx.inputs.get("os_type") or "linux").strip().lower()
    if os_type not in ("linux", "windows", "darwin"):
        raise ValueError(f"Unsupported os_type: '{os_type}'")

    section_name = str(ctx.inputs.get("section_name") or "system-info").strip()
    capture = str(ctx.inputs.get("capture") or "")

    run_dir = _run_dir(ctx)
    report = os.path.join(run_dir, f"{os_type}_recon_report.txt")
    with open(report, "w", encoding="utf-8") as handle:
        handle.write(f"# {os_type} situational awareness report\n")
        handle.write(f"# host: {os.uname().nodename}\n")
        handle.write(
            f"# generated: {datetime.now(UTC).isoformat(timespec='seconds')}\n"
        )
        handle.write(f"\n===== {section_name} =====\n")
        handle.write(capture if capture.endswith("\n") or not capture else capture + "\n")

    if not capture.strip():
        raise RuntimeError(
            f"No output captured for section '{section_name}'; "
            f"the enumeration step produced nothing (report: {report})"
        )

    sections = [section_name]
    print(f"[+] Report written to {report} ({len(capture)} bytes)")
    ctx.add_outputs(
        report_path=report,
        os_type=os_type,
        sections=sections,
        section_sizes={section_name: len(capture)},
    )
