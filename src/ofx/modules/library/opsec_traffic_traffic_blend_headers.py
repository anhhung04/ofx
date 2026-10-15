"""Module wrapper for ``ofx.api.opsec.traffic.traffic_blend_headers``."""

from __future__ import annotations

from typing import Any

name = "opsec.traffic.traffic_blend_headers"
description = "Return HTTP headers that blend C2/recon traffic with normal browser requests."
args_schema: dict[str, Any] = {
        "referer": {"type": "string", "default": 'https://www.google.com'},
}


def run(ctx):
    """Call ofx.api.opsec.traffic.traffic_blend_headers with the module's arguments."""
    from ofx.api.opsec.traffic import traffic_blend_headers as _func

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
