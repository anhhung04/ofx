"""Module wrapper for ``ofx.api.httpserver.exfil.build_exfil_handler``."""

from __future__ import annotations

from typing import Any

name = "httpserver.exfil.build_exfil_handler"
description = "Create a request handler with injected upload directory."
args_schema: dict[str, Any] = {
        "upload_dir": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.api.httpserver.exfil.build_exfil_handler with the module's arguments."""
    from ofx.api.httpserver.exfil import build_exfil_handler as _func

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
