"""Module wrapper for ``ofx.lib.evasion.jitter.sleep_with_jitter``."""

from __future__ import annotations

from typing import Any

name = "evasion.jitter.sleep_with_jitter"
description = "Sleep for a jittered interval and return the actual delay."
args_schema: dict[str, Any] = {
        "base_seconds": {"type": "string", "required": True},
        "jitter_pct": {"type": "string", "default": 0.2},
}


def run(ctx):
    """Call ofx.lib.evasion.jitter.sleep_with_jitter with the module's arguments."""
    from ofx.lib.evasion.jitter import sleep_with_jitter as _func

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
