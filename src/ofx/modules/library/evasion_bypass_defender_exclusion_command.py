"""Module wrapper for ``ofx.api.evasion.bypass.defender_exclusion_command``."""

from __future__ import annotations

from typing import Any

name = "evasion.bypass.defender_exclusion_command"
description = "Return a PowerShell command to add a Defender path exclusion (requires admin)."
args_schema: dict[str, Any] = {
        "path": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.api.evasion.bypass.defender_exclusion_command with the module's arguments."""
    from ofx.api.evasion.bypass import defender_exclusion_command as _func

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
