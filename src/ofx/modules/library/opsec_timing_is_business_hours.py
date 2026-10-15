"""Module wrapper for ``ofx.api.opsec.timing.is_business_hours``."""

from __future__ import annotations

from typing import Any

name = "opsec.timing.is_business_hours"
description = "Return True if the current UTC time (adjusted by *tz_offset* hours) is within business hours."
args_schema: dict[str, Any] = {
        "tz_offset": {"type": "string", "default": 0},
        "start": {"type": "string", "default": 9},
        "end": {"type": "string", "default": 17},
        "include_weekends": {"type": "string", "default": False},
}


def run(ctx):
    """Call ofx.api.opsec.timing.is_business_hours with the module's arguments."""
    from ofx.api.opsec.timing import is_business_hours as _func

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
