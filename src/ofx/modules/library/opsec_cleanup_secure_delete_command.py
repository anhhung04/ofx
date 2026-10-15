"""Module wrapper for ``ofx.lib.opsec.cleanup.secure_delete_command``."""

from __future__ import annotations

from typing import Any

name = "opsec.cleanup.secure_delete_command"
description = "Return a shred command for secure file deletion."
args_schema: dict[str, Any] = {
        "path": {"type": "string", "required": True},
        "passes": {"type": "string", "default": 3},
        "recursive": {"type": "string", "default": False},
}


def run(ctx):
    """Call ofx.lib.opsec.cleanup.secure_delete_command with the module's arguments."""
    from ofx.lib.opsec.cleanup import secure_delete_command as _func

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
