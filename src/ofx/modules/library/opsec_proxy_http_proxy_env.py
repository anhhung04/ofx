"""Module wrapper for ``ofx.lib.opsec.proxy.http_proxy_env``."""

from __future__ import annotations

from typing import Any

name = "opsec.proxy.http_proxy_env"
description = "Return an env vars dict to route HTTP/HTTPS through a proxy."
args_schema: dict[str, Any] = {
        "host": {"type": "string", "required": True},
        "port": {"type": "string", "required": True},
        "scheme": {"type": "string", "default": 'socks5'},
        "user": {"type": "string", "default": ''},
        "password": {"type": "string", "default": ''},
}


def run(ctx):
    """Call ofx.lib.opsec.proxy.http_proxy_env with the module's arguments."""
    from ofx.lib.opsec.proxy import http_proxy_env as _func

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
