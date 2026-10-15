"""Module wrapper for ``ofx.api.opsec.timing.random_sleep_seconds``."""

from __future__ import annotations

from typing import Any

name = "opsec.timing.random_sleep_seconds"
description = "Return a random sleep duration between *min_s* and *max_s* seconds."
args_schema: dict[str, Any] = {
        "min_s": {"type": "string", "required": True},
        "max_s": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.api.opsec.timing.random_sleep_seconds with the module's arguments."""
    from ofx.api.opsec.timing import random_sleep_seconds as _func

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
