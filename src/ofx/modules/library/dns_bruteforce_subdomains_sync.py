"""Module wrapper for ``ofx.lib.dns.bruteforce_subdomains_sync``."""

from __future__ import annotations

from typing import Any

name = "dns.bruteforce_subdomains_sync"
description = 'Sync wrapper for subdomain brute-force.'
args_schema: dict[str, Any] = {
        'domain': {'type': 'string', 'required': True},
        'candidates': {'type': 'string', 'required': True},
        'concurrency': {'type': 'integer', 'default': 100},
        'timeout': {'type': 'number', 'default': 2.0},
        'jitter': {'type': 'number', 'default': 0.0},
}


def run(ctx):
    """Call ofx.lib.dns.bruteforce_subdomains_sync with the module's arguments."""
    from ofx.lib.dns import bruteforce_subdomains_sync as _func

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
