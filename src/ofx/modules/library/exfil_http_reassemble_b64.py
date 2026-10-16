"""Module wrapper for ``ofx.lib.exfil.http.reassemble_b64``."""

from __future__ import annotations

from typing import Any

name = "exfil.http.reassemble_b64"
description = "Reassemble base64-encoded chunks produced by :func:`chunk_b64`."
args_schema: dict[str, Any] = {
        "chunks": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.lib.exfil.http.reassemble_b64 with the module's arguments."""
    from ofx.lib.exfil.http import reassemble_b64 as _func

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
