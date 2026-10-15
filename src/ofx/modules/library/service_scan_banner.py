"""Module wrapper for ``ofx.lib.service.scan_banner``."""

from __future__ import annotations

from typing import Any

name = "service.scan_banner"
description = 'Grab a simple banner and guess protocol.'
args_schema: dict[str, Any] = {
        'host': {'type': 'string', 'required': True},
        'port': {'type': 'integer', 'required': True},
        'timeout': {'type': 'number', 'default': 3.0},
        'tls': {'type': 'boolean', 'default': 'None'},
        'max_bytes': {'type': 'integer', 'default': 1024},
}


def run(ctx):
    """Call ofx.lib.service.scan_banner with the module's arguments."""
    from ofx.lib.service import scan_banner as _func

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
