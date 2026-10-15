"""Module wrapper for ``ofx.lib.service.detect_protocol``."""

from __future__ import annotations

from typing import Any

name = "service.detect_protocol"
description = 'ofx.lib.service.detect_protocol'
args_schema: dict[str, Any] = {
        'port': {'type': 'integer', 'required': True},
        'banner': {'type': 'string', 'default': 'None'},
}


def run(ctx):
    """Call ofx.lib.service.detect_protocol with the module's arguments."""
    from ofx.lib.service import detect_protocol as _func

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
