"""Module wrapper for ``ofx.lib.network.bind_telnet_shell``."""

from __future__ import annotations

from typing import Any

name = "network.bind_telnet_shell"
description = 'Create a telnet-style bind shell on port 23.'
args_schema: dict[str, Any] = {
        'host': {'type': 'string', 'default': '0.0.0.0'},
        'port': {'type': 'integer', 'default': 23},
}


def run(ctx):
    """Call ofx.lib.network.bind_telnet_shell with the module's arguments."""
    from ofx.lib.network import bind_telnet_shell as _func

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
