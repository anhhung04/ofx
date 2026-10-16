"""Module wrapper for ``ofx.lib.recon.osint.crtsh_subdomains_sync``."""

from __future__ import annotations

from typing import Any

name = "recon.osint.crtsh_subdomains_sync"
description = "Synchronous wrapper around :func:`crtsh_subdomains`."
args_schema: dict[str, Any] = {
        "domain": {"type": "string", "required": True},
        "timeout": {"type": "string", "default": 15.0},
}


def run(ctx):
    """Call ofx.lib.recon.osint.crtsh_subdomains_sync with the module's arguments."""
    from ofx.lib.recon.osint import crtsh_subdomains_sync as _func

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
