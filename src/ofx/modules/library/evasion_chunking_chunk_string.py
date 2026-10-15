"""Module wrapper for ``ofx.api.evasion.chunking.chunk_string``."""

from __future__ import annotations

from typing import Any

name = "evasion.chunking.chunk_string"
description = "Split a string into fixed-size chunks."
args_schema: dict[str, Any] = {
        "value": {"type": "string", "required": True},
        "size": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.api.evasion.chunking.chunk_string with the module's arguments."""
    from ofx.api.evasion.chunking import chunk_string as _func

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
