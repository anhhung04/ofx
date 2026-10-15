"""Module wrapper for ``ofx.api.privesc.windows.uac_bypass_commands``."""

from __future__ import annotations

from typing import Any

name = "privesc.windows.uac_bypass_commands"
description = "Return UAC bypass commands for the specified technique."
args_schema: dict[str, Any] = {
        "technique": {"type": "string", "default": 'fodhelper'},
        "payload": {"type": "string", "default": 'cmd.exe'},
}


def run(ctx):
    """Call ofx.api.privesc.windows.uac_bypass_commands with the module's arguments."""
    from ofx.api.privesc.windows import uac_bypass_commands as _func

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
