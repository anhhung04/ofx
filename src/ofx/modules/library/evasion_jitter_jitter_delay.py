"""Module wrapper for ``ofx.api.evasion.jitter.jitter_delay``."""

from __future__ import annotations

from typing import Any

name = "evasion.jitter.jitter_delay"
description = "Return a delay with +/- jitter."
args_schema: dict[str, Any] = {
        "base_seconds": {"type": "string", "required": True},
        "jitter_pct": {"type": "string", "default": 0.2},
        "rng": {"type": "string", "default": None},
}


def run(ctx):
    """Call ofx.api.evasion.jitter.jitter_delay with the module's arguments."""
    from ofx.api.evasion.jitter import jitter_delay as _func

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
