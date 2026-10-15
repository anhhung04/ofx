"""Module wrapper for ``ofx.lib.httpserver.payload.build_payload_handler``."""

from __future__ import annotations

from typing import Any

name = "httpserver.payload.build_payload_handler"
description = "Create a request handler with injected payload dependencies."
args_schema: dict[str, Any] = {
        "payload_path": {"type": "string", "required": True},
        "payloads": {"type": "string", "required": True},
        "hits": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.lib.httpserver.payload.build_payload_handler with the module's arguments."""
    from ofx.lib.httpserver.payload import build_payload_handler as _func

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
