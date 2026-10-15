"""Module wrapper for ``ofx.lib.data.archive_path``."""

from __future__ import annotations

from typing import Any

name = "data.archive_path"
description = "ofx.lib data.archive_path"
args_schema: dict[str, Any] = {
        "src": {"type": "string", "required": True},
        "output": {"type": "string", "default": None},
        "fmt": {"type": "string", "default": 'zip'},
}


def run(ctx):
    """Call ofx.lib.data.archive_path with the module's arguments."""
    from ofx.lib.data import archive_path as _func

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
