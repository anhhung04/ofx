"""Module wrapper for ``ofx.api.ad.execution.secretsdump_command``."""

from __future__ import annotations

from typing import Any

name = "ad.execution.secretsdump_command"
description = "Build an impacket secretsdump command to dump credentials from a DC."
args_schema: dict[str, Any] = {
        "target": {"type": "string", "required": True},
        "username": {"type": "string", "required": True},
        "password": {"type": "string", "required": True},
        "domain": {"type": "string", "default": '.'},
        "just_dc_ntlm": {"type": "string", "default": True},
        "output": {"type": "string", "default": 'dump'},
}


def run(ctx):
    """Call ofx.api.ad.execution.secretsdump_command with the module's arguments."""
    from ofx.api.ad.execution import secretsdump_command as _func

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
