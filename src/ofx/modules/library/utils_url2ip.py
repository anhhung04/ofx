"""Module wrapper for ``ofx.api.utils.url2ip``."""

from __future__ import annotations

from typing import Any

name = "utils.url2ip"
description = "Convert a URL to an IP address with optional port."
args_schema: dict[str, Any] = {
        "url": {"type": "string", "required": True},
        "with_port": {"type": "boolean", "default": False},
}


def run(ctx):
    """Call ofx.api.utils.url2ip with the module's arguments."""
    from ofx.api.utils import url2ip as _func

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
        from ofx.modules.api import ApiModuleError

        raise ApiModuleError(
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
