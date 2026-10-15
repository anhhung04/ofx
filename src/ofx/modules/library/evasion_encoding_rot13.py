"""Module wrapper for ``ofx.lib.evasion.encoding.rot13``."""

from __future__ import annotations

from typing import Any

name = "evasion.encoding.rot13"
description = "Apply ROT13 to ASCII letters."
args_schema: dict[str, Any] = {
        "text": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.lib.evasion.encoding.rot13 with the module's arguments."""
    from ofx.lib.evasion.encoding import rot13 as _func

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
