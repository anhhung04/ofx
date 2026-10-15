"""Module wrapper for ``ofx.api.evasion.payload.obfuscate_cmd``."""

from __future__ import annotations

from typing import Any

name = "evasion.payload.obfuscate_cmd"
description = "Obfuscate Windows CMD command using caret insertion."
args_schema: dict[str, Any] = {
        "command": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.api.evasion.payload.obfuscate_cmd with the module's arguments."""
    from ofx.api.evasion.payload import obfuscate_cmd as _func

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
