"""Module wrapper for ``ofx.api.recon.osint.whois_command``."""

from __future__ import annotations

from typing import Any

name = "recon.osint.whois_command"
description = "Return a whois command for a domain or IP address."
args_schema: dict[str, Any] = {
        "target": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.api.recon.osint.whois_command with the module's arguments."""
    from ofx.api.recon.osint import whois_command as _func

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
