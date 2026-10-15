"""Module wrapper for ``ofx.api.evasion.encoding.xor_bytes``."""

from __future__ import annotations

from typing import Any

name = "evasion.encoding.xor_bytes"
description = "XOR bytes with a single-byte key."
args_schema: dict[str, Any] = {
        "data": {"type": "string", "required": True},
        "key": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.api.evasion.encoding.xor_bytes with the module's arguments."""
    from ofx.api.evasion.encoding import xor_bytes as _func

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
