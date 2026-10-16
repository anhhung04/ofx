"""Module wrapper for ``ofx.lib.httpserver.utils.start_server``."""

from __future__ import annotations

from typing import Any

name = "httpserver.utils.start_server"
description = "Start an HTTP server of the specified type."
args_schema: dict[str, Any] = {
        "server_type": {"type": "string", "required": True},
        "host": {"type": "string", "default": '0.0.0.0'},
        "port": {"type": "string", "default": 6666},
}


def run(ctx):
    """Call ofx.lib.httpserver.utils.start_server with the module's arguments."""
    from ofx.lib.httpserver.utils import start_server as _func

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
