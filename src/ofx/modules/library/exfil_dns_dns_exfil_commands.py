"""Module wrapper for ``ofx.api.exfil.dns.dns_exfil_commands``."""

from __future__ import annotations

from typing import Any

name = "exfil.dns.dns_exfil_commands"
description = "Return shell commands to exfiltrate *data* via DNS lookups."
args_schema: dict[str, Any] = {
        "data": {"type": "string", "required": True},
        "domain": {"type": "string", "required": True},
        "label_max": {"type": "string", "default": 60},
        "tool": {"type": "string", "default": 'dig'},
}


def run(ctx):
    """Call ofx.api.exfil.dns.dns_exfil_commands with the module's arguments."""
    from ofx.api.exfil.dns import dns_exfil_commands as _func

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
