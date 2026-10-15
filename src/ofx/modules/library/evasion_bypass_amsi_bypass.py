"""Module wrapper for ``ofx.api.evasion.bypass.amsi_bypass``."""

from __future__ import annotations

from typing import Any

name = "evasion.bypass.amsi_bypass"
description = "Return a PowerShell AMSI bypass snippet."
args_schema: dict[str, Any] = {
        "technique": {"type": "string", "default": 'reflection'},
}


def run(ctx):
    """Call ofx.api.evasion.bypass.amsi_bypass with the module's arguments."""
    from ofx.api.evasion.bypass import amsi_bypass as _func

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
