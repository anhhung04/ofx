"""Module wrapper for ``ofx.api.exfil.http.chunk_b64``."""

from __future__ import annotations

from typing import Any

name = "exfil.http.chunk_b64"
description = "Split *data* into base64-encoded chunks for staged exfiltration."
args_schema: dict[str, Any] = {
        "data": {"type": "string", "required": True},
        "chunk_size": {"type": "string", "default": 2048},
}


def run(ctx):
    """Call ofx.api.exfil.http.chunk_b64 with the module's arguments."""
    from ofx.api.exfil.http import chunk_b64 as _func

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
