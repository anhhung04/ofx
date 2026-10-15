"""Module wrapper for ``ofx.lib.recon.targets.classify_target``."""

from __future__ import annotations

from typing import Any

name = "recon.targets.classify_target"
description = "Classify a single target string."
args_schema: dict[str, Any] = {
        "value": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.lib.recon.targets.classify_target with the module's arguments."""
    from ofx.lib.recon.targets import classify_target as _func

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
