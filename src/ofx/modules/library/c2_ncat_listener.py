"""Module wrapper for ``ofx.lib.c2.ncat_listener``."""

from __future__ import annotations

from typing import Any

name = "c2.ncat_listener"
description = "Return a netcat/ncat listener command."
args_schema: dict[str, Any] = {
        "port": {"type": "string", "required": True},
        "ssl": {"type": "string", "default": False},
        "verbose": {"type": "string", "default": False},
}


def run(ctx):
    """Call ofx.lib.c2.ncat_listener with the module's arguments."""
    from ofx.lib.c2 import ncat_listener as _func

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
