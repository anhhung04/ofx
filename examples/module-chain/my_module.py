"""Example user-defined module for OFX workflows.

Contract: a callable taking a ModuleContext (`ctx`) with:
  - ctx.inputs       — the step's `with:` args (dict)
  - ctx.secrets      — resolved secrets (dict)
  - ctx.env          — environment variables (dict)
  - ctx.working_directory — Path of the step working directory
  - ctx.add_outputs(**kwargs) — merge keys into step outputs
  - ctx.log(msg)     — log through the step logger
Return None or a dict (merged into step outputs).
Raise to fail the step (traceback captured into the step error).
"""

from __future__ import annotations

from typing import Any


def run(ctx) -> dict[str, Any]:
    """Classify open ports into an attack plan (toy UDF example)."""
    ports = ctx.inputs.get("ports", [])
    if isinstance(ports, str):
        ports = [p.strip() for p in ports.split(",") if p.strip()]
    ctx.log(f"planning attacks for {len(ports)} open port(s)")

    plan = []
    for port in ports:
        service = {"22": "ssh", "80": "http", "443": "https", "445": "smb"}.get(
            str(port), "unknown"
        )
        plan.append({"port": str(port), "service": service})

    ctx.add_outputs(planned=len(plan))
    return {"plan": plan}
