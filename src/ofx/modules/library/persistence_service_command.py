"""Module wrapper for ``ofx.lib.persistence.service_command``."""

from __future__ import annotations

from typing import Any

name = "persistence.service_command"
description = "ofx.lib persistence.service_command"
args_schema: dict[str, Any] = {
        "name": {"type": "string", "required": True},
        "bin_path": {"type": "string", "required": True},
        "display_name": {"type": "string", "default": None},
}


def run(ctx):
    """Call ofx.lib.persistence.service_command with the module's arguments."""
    from ofx.lib.persistence import service_command as _func

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
