"""Module wrapper for ``ofx.api.persistence.motd_persistence``."""

from __future__ import annotations

from typing import Any

name = "persistence.motd_persistence"
description = "Return commands to inject persistence via ``/etc/update-motd.d/`` (requires root)."
args_schema: dict[str, Any] = {
        "cmd": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.api.persistence.motd_persistence with the module's arguments."""
    from ofx.api.persistence import motd_persistence as _func

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
