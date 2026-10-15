"""Module wrapper for ``ofx.api.ad.kerberos.golden_ticket_command``."""

from __future__ import annotations

from typing import Any

name = "ad.kerberos.golden_ticket_command"
description = "Return impacket ticketer commands to forge a Golden Ticket."
args_schema: dict[str, Any] = {
        "domain": {"type": "string", "required": True},
        "domain_sid": {"type": "string", "required": True},
        "krbtgt_hash": {"type": "string", "required": True},
        "target_user": {"type": "string", "default": 'Administrator'},
        "output": {"type": "string", "default": None},
}


def run(ctx):
    """Call ofx.api.ad.kerberos.golden_ticket_command with the module's arguments."""
    from ofx.api.ad.kerberos import golden_ticket_command as _func

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
