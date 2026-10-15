"""Module wrapper for ``ofx.api.opsec.cleanup.clean_linux_logs``."""

from __future__ import annotations

from typing import Any

name = "opsec.cleanup.clean_linux_logs"
description = "Return commands to clear common Linux log artefacts."
args_schema: dict[str, Any] = {
        "aggressive": {"type": "string", "default": False},
}


def run(ctx):
    """Call ofx.api.opsec.cleanup.clean_linux_logs with the module's arguments."""
    from ofx.api.opsec.cleanup import clean_linux_logs as _func

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
