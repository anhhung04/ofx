"""Module wrapper for ``ofx.lib.evasion.bypass.etw_bypass``."""

from __future__ import annotations

from typing import Any

name = "evasion.bypass.etw_bypass"
description = 'Return a PowerShell snippet that patches EtwEventWrite to suppress ETW telemetry.'
args_schema: dict[str, Any] = {}


def run(ctx):
    """Call ofx.lib.evasion.bypass.etw_bypass with the module's arguments."""
    from ofx.lib.evasion.bypass import etw_bypass as _func

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
