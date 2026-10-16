"""Module wrapper for ``ofx.lib.payloads.build_lnk``."""

from __future__ import annotations

from typing import Any

name = "payloads.build_lnk"
description = 'Return a PowerShell snippet that creates a LNK pointing to `command`.'
args_schema: dict[str, Any] = {
        'command': {'type': 'string', 'required': True},
        'icon': {'type': 'string', 'default': 'None'},
        'workdir': {'type': 'string', 'default': 'None'},
}


def run(ctx):
    """Call ofx.lib.payloads.build_lnk with the module's arguments."""
    from ofx.lib.payloads import build_lnk as _func

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
