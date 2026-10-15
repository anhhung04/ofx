"""Module wrapper for ``ofx.api.ad.enum.enumerate_shares_command``."""

from __future__ import annotations

from typing import Any

name = "ad.enum.enumerate_shares_command"
description = "Build a netexec command to enumerate SMB shares and check access."
args_schema: dict[str, Any] = {
        "target": {"type": "string", "required": True},
        "username": {"type": "string", "required": True},
        "password": {"type": "string", "required": True},
        "domain": {"type": "string", "default": '.'},
}


def run(ctx):
    """Call ofx.api.ad.enum.enumerate_shares_command with the module's arguments."""
    from ofx.api.ad.enum import enumerate_shares_command as _func

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
