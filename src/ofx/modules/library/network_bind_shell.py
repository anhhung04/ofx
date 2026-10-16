"""Module wrapper for ``ofx.lib.network.bind_shell``."""

from __future__ import annotations

from typing import Any

name = "network.bind_shell"
description = 'Create a bind shell that listens for incoming connections.'
args_schema: dict[str, Any] = {
        'host': {'type': 'string', 'default': '0.0.0.0'},
        'port': {'type': 'integer', 'default': 4444},
        'shell': {'type': 'string', 'default': '/bin/sh'},
}


def run(ctx):
    """Call ofx.lib.network.bind_shell with the module's arguments."""
    from ofx.lib.network import bind_shell as _func

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
