"""Module wrapper for ``ofx.lib.exfil.http.icmp_exfil_command``."""

from __future__ import annotations

from typing import Any

name = "exfil.http.icmp_exfil_command"
description = "Build a command for ICMP payload-based data exfiltration."
args_schema: dict[str, Any] = {
        "data": {"type": "string", "required": True},
        "destination": {"type": "string", "required": True},
        "tool": {"type": "string", "default": 'hping3'},
}


def run(ctx):
    """Call ofx.lib.exfil.http.icmp_exfil_command with the module's arguments."""
    from ofx.lib.exfil.http import icmp_exfil_command as _func

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
