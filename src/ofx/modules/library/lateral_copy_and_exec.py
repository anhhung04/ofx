"""Module wrapper for ``ofx.lib.lateral.copy_and_exec``."""

from __future__ import annotations

from typing import Any

name = "lateral.copy_and_exec"
description = "Upload a file then execute it via a registered post runner."
args_schema: dict[str, Any] = {
        "target": {"type": "string", "required": True},
        "src": {"type": "string", "required": True},
        "dst": {"type": "string", "required": True},
        "method": {"type": "string", "default": 'smbexec'},
        "command": {"type": "string", "default": None},
}


def run(ctx):
    """Call ofx.lib.lateral.copy_and_exec with the module's arguments."""
    from ofx.lib.lateral import copy_and_exec as _func

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
