"""Module wrapper for ``ofx.api.persistence.crontab_command``."""

from __future__ import annotations

from typing import Any

name = "persistence.crontab_command"
description = "Return commands to install a Linux crontab persistence entry."
args_schema: dict[str, Any] = {
        "cmd": {"type": "string", "required": True},
        "schedule": {"type": "string", "default": '@reboot'},
        "user": {"type": "string", "default": ''},
}


def run(ctx):
    """Call ofx.api.persistence.crontab_command with the module's arguments."""
    from ofx.api.persistence import crontab_command as _func

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
