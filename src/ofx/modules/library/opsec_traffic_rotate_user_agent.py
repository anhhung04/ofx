"""Module wrapper for ``ofx.lib.opsec.traffic.rotate_user_agent``."""

from __future__ import annotations

from typing import Any

name = "opsec.traffic.rotate_user_agent"
description = 'Return a random realistic browser User-Agent string.'
args_schema: dict[str, Any] = {}


def run(ctx):
    """Call ofx.lib.opsec.traffic.rotate_user_agent with the module's arguments."""
    from ofx.lib.opsec.traffic import rotate_user_agent as _func

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
