"""Module wrapper for ``ofx.lib.persistence.schtask_command``."""

from __future__ import annotations

from typing import Any

name = "persistence.schtask_command"
description = "ofx.lib persistence.schtask_command"
args_schema: dict[str, Any] = {
        "name": {"type": "string", "required": True},
        "cmd": {"type": "string", "required": True},
        "trigger": {"type": "string", "default": 'ONLOGON'},
        "user": {"type": "string", "default": None},
}


def run(ctx):
    """Call ofx.lib.persistence.schtask_command with the module's arguments."""
    from ofx.lib.persistence import schtask_command as _func

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
