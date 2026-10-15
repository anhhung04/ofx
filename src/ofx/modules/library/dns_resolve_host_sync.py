"""Module wrapper for ``ofx.lib.dns.resolve_host_sync``."""

from __future__ import annotations

from typing import Any

name = "dns.resolve_host_sync"
description = 'Synchronous resolver wrapper.'
args_schema: dict[str, Any] = {
        'host': {'type': 'string', 'required': True},
        'timeout': {'type': 'number', 'default': 2.0},
}


def run(ctx):
    """Call ofx.lib.dns.resolve_host_sync with the module's arguments."""
    from ofx.lib.dns import resolve_host_sync as _func

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
