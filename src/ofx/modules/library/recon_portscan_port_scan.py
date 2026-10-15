"""Module wrapper for ``ofx.lib.recon.portscan.port_scan``."""

from __future__ import annotations

from typing import Any

name = "recon.portscan.port_scan"
description = "Synchronous wrapper around :func:`async_port_scan`."
args_schema: dict[str, Any] = {
        "host": {"type": "string", "required": True},
        "ports": {"type": "string", "default": None},
        "concurrency": {"type": "string", "default": 250},
        "timeout": {"type": "string", "default": 1.5},
}


def run(ctx):
    """Call ofx.lib.recon.portscan.port_scan with the module's arguments."""
    from ofx.lib.recon.portscan import port_scan as _func

    kwargs = {}
    missing = []
    for key, spec in args_schema.items():
        value = ctx.args.get(key, ctx.inputs.get(key))
        if value is not None:
            kwargs[key] = value
        elif spec.get("required"):
            missing.append(key)
    if missing:
        received = ", ".join(sorted(ctx.args)) or "(none)"
        from ofx.modules.libref import LibModuleError

        raise LibModuleError(
            f"Missing required argument(s): {', '.join(missing)}. "
            f"Received keys: {received}"
        )
    result = _func(**kwargs)
    if result is not None:
        if isinstance(result, dict):
            ctx.add_outputs(**result)
        else:
            ctx.add_outputs(result=result)
    return result
