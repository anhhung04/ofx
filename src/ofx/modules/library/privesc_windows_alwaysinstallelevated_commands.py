"""Module wrapper for ``ofx.lib.privesc.windows.alwaysinstallelevated_commands``."""

from __future__ import annotations

from typing import Any

name = "privesc.windows.alwaysinstallelevated_commands"
description = 'Return registry queries to check for AlwaysInstallElevated misconfiguration.'
args_schema: dict[str, Any] = {}


def run(ctx):
    """Call ofx.lib.privesc.windows.alwaysinstallelevated_commands with the module's arguments."""
    from ofx.lib.privesc.windows import alwaysinstallelevated_commands as _func

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
