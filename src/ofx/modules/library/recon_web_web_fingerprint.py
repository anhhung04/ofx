"""Module wrapper for ``ofx.api.recon.web.web_fingerprint``."""

from __future__ import annotations

from typing import Any

name = "recon.web.web_fingerprint"
description = "Detect web technologies from HTTP response headers."
args_schema: dict[str, Any] = {
        "headers": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.api.recon.web.web_fingerprint with the module's arguments."""
    from ofx.api.recon.web import web_fingerprint as _func

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
