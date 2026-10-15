"""Module wrapper for ``ofx.lib.httpserver.utils.create_oneliner``."""

from __future__ import annotations

from typing import Any

name = "httpserver.utils.create_oneliner"
description = "Create a one-liner command for downloading and executing a payload."
args_schema: dict[str, Any] = {
        "url": {"type": "string", "required": True},
        "method": {"type": "string", "default": 'curl'},
}


def run(ctx):
    """Call ofx.lib.httpserver.utils.create_oneliner with the module's arguments."""
    from ofx.lib.httpserver.utils import create_oneliner as _func

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
