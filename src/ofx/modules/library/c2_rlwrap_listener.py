"""Module wrapper for ``ofx.api.c2.rlwrap_listener``."""

from __future__ import annotations

from typing import Any

name = "c2.rlwrap_listener"
description = "Return an rlwrap-wrapped nc listener for improved interactive shell handling."
args_schema: dict[str, Any] = {
        "port": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.api.c2.rlwrap_listener with the module's arguments."""
    from ofx.api.c2 import rlwrap_listener as _func

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
