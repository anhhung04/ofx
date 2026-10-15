"""Module wrapper for ``ofx.api.ad.execution.spray_command``."""

from __future__ import annotations

from typing import Any

name = "ad.execution.spray_command"
description = "Build a netexec password spraying command."
args_schema: dict[str, Any] = {
        "dc_ip": {"type": "string", "required": True},
        "domain": {"type": "string", "required": True},
        "password": {"type": "string", "required": True},
        "users_file": {"type": "string", "required": True},
        "protocol": {"type": "string", "default": 'smb'},
        "jitter_s": {"type": "string", "default": 0},
}


def run(ctx):
    """Call ofx.api.ad.execution.spray_command with the module's arguments."""
    from ofx.api.ad.execution import spray_command as _func

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
