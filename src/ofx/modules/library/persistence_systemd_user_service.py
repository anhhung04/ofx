"""Module wrapper for ``ofx.api.persistence.systemd_user_service``."""

from __future__ import annotations

from typing import Any

name = "persistence.systemd_user_service"
description = "Return commands to install a persistent systemd service."
args_schema: dict[str, Any] = {
        "name": {"type": "string", "required": True},
        "exec_start": {"type": "string", "required": True},
        "description": {"type": "string", "default": 'System Update Service'},
        "restart": {"type": "string", "default": 'always'},
        "system_wide": {"type": "string", "default": False},
}


def run(ctx):
    """Call ofx.api.persistence.systemd_user_service with the module's arguments."""
    from ofx.api.persistence import systemd_user_service as _func

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
