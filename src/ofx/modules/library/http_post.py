"""Module wrapper for ``ofx.lib.http.post``."""

from __future__ import annotations

from typing import Any

name = "http.post"
description = 'Send a POST request with retry logic and connection pooling.'
args_schema: dict[str, Any] = {
        'url': {'type': 'string', 'required': True},
        'data': {'type': 'object', 'required': True},
        'max_retries': {'type': 'integer', 'default': 3},
        'timeout': {'type': 'integer', 'default': 30},
        'rate_limit': {'type': 'number', 'default': 'None'},
}


def run(ctx):
    """Call ofx.lib.http.post with the module's arguments."""
    from ofx.lib.http import post as _func

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
