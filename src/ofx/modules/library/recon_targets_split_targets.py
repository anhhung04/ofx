"""Module wrapper for ``ofx.lib.recon.targets.split_targets``."""

from __future__ import annotations

from typing import Any

name = "recon.targets.split_targets"
description = "Split target strings into a ``{type: [values]}`` dict."
args_schema: dict[str, Any] = {
        "values": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.lib.recon.targets.split_targets with the module's arguments."""
    from ofx.lib.recon.targets import split_targets as _func

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
