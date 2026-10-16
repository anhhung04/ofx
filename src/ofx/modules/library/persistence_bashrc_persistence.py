"""Module wrapper for ``ofx.lib.persistence.bashrc_persistence``."""

from __future__ import annotations

from typing import Any

name = "persistence.bashrc_persistence"
description = "Return commands to append a persistent entry to ``.bashrc`` or ``.profile``."
args_schema: dict[str, Any] = {
        "cmd": {"type": "string", "required": True},
        "profile": {"type": "string", "default": False},
}


def run(ctx):
    """Call ofx.lib.persistence.bashrc_persistence with the module's arguments."""
    from ofx.lib.persistence import bashrc_persistence as _func

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
