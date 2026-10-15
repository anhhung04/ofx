"""Module wrapper for ``ofx.api.post.transfer.build_download_command``."""

from __future__ import annotations

from typing import Any

name = "post.transfer.build_download_command"
description = "Build a best-effort download command for a target platform."
args_schema: dict[str, Any] = {
        "url": {"type": "string", "required": True},
        "dest": {"type": "string", "required": True},
        "platform": {"type": "string", "default": 'unix'},
}


def run(ctx):
    """Call ofx.api.post.transfer.build_download_command with the module's arguments."""
    from ofx.api.post.transfer import build_download_command as _func

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
