"""Module wrapper for ``ofx.lib.opsec.cleanup.clean_history_commands``."""

from __future__ import annotations

from typing import Any

name = "opsec.cleanup.clean_history_commands"
description = 'Return shell commands that wipe common Linux shell history artefacts.'
args_schema: dict[str, Any] = {}


def run(ctx):
    """Call ofx.lib.opsec.cleanup.clean_history_commands with the module's arguments."""
    from ofx.lib.opsec.cleanup import clean_history_commands as _func

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
