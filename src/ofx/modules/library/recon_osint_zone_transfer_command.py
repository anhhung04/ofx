"""Module wrapper for ``ofx.api.recon.osint.zone_transfer_command``."""

from __future__ import annotations

from typing import Any

name = "recon.osint.zone_transfer_command"
description = "Return a dig AXFR command attempting a DNS zone transfer."
args_schema: dict[str, Any] = {
        "domain": {"type": "string", "required": True},
        "nameserver": {"type": "string", "default": ''},
}


def run(ctx):
    """Call ofx.api.recon.osint.zone_transfer_command with the module's arguments."""
    from ofx.api.recon.osint import zone_transfer_command as _func

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
