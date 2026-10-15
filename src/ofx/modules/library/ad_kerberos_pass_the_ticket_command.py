"""Module wrapper for ``ofx.lib.ad.kerberos.pass_the_ticket_command``."""

from __future__ import annotations

from typing import Any

name = "ad.kerberos.pass_the_ticket_command"
description = "Return commands to use a Kerberos ccache for Pass-the-Ticket execution."
args_schema: dict[str, Any] = {
        "ccache_file": {"type": "string", "required": True},
        "target": {"type": "string", "required": True},
        "username": {"type": "string", "required": True},
        "domain": {"type": "string", "required": True},
        "command": {"type": "string", "default": 'whoami /all'},
        "method": {"type": "string", "default": 'wmiexec'},
}


def run(ctx):
    """Call ofx.lib.ad.kerberos.pass_the_ticket_command with the module's arguments."""
    from ofx.lib.ad.kerberos import pass_the_ticket_command as _func

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
