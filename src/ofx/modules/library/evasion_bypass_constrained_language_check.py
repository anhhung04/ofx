"""Module wrapper for ``ofx.lib.evasion.bypass.constrained_language_check``."""

from __future__ import annotations

from typing import Any

name = "evasion.bypass.constrained_language_check"
description = 'Return a PowerShell command to check if Constrained Language Mode is active.'
args_schema: dict[str, Any] = {}


def run(ctx):
    """Call ofx.lib.evasion.bypass.constrained_language_check with the module's arguments."""
    from ofx.lib.evasion.bypass import constrained_language_check as _func

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
