"""Module wrapper for ``ofx.api.recon.osint.crtsh_subdomains``."""

from __future__ import annotations

from typing import Any

name = "recon.osint.crtsh_subdomains"
description = "Query crt.sh certificate transparency logs for subdomains of *domain*."
args_schema: dict[str, Any] = {
        "domain": {"type": "string", "required": True},
        "timeout": {"type": "string", "default": 15.0},
}


def run(ctx):
    """Call ofx.api.recon.osint.crtsh_subdomains with the module's arguments."""
    from ofx.api.recon.osint import crtsh_subdomains as _func

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
        from ofx.modules.api import ApiModuleError

        raise ApiModuleError(
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
