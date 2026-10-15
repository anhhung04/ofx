"""Module wrapper for ``ofx.lib.opsec.proxy.build_proxychains_conf``."""

from __future__ import annotations

from typing import Any

name = "opsec.proxy.build_proxychains_conf"
description = "Build a proxychains4.conf content string."
args_schema: dict[str, Any] = {
        "proxies": {"type": "string", "required": True},
        "chain_type": {"type": "string", "default": 'dynamic_chain'},
        "proxy_dns": {"type": "string", "default": True},
}


def run(ctx):
    """Call ofx.lib.opsec.proxy.build_proxychains_conf with the module's arguments."""
    from ofx.lib.opsec.proxy import build_proxychains_conf as _func

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
