"""Module wrapper for ``ofx.api.post.enum.winpeas_command``."""

from __future__ import annotations

from typing import Any

name = "post.enum.winpeas_command"
description = "Build a command to run winPEAS."
args_schema: dict[str, Any] = {
        "url": {"type": "string", "default": None},
        "dest": {"type": "string", "default": 'C:\\Windows\\Temp\\winpeas.exe'},
        "prefer_local": {"type": "string", "default": True},
        "local_path": {"type": "string", "default": None},
}


def run(ctx):
    """Call ofx.api.post.enum.winpeas_command with the module's arguments."""
    from ofx.api.post.enum import winpeas_command as _func

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
