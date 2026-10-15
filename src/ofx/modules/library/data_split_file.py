"""Module wrapper for ``ofx.api.data.split_file``."""

from __future__ import annotations

from typing import Any

name = "data.split_file"
description = "ofx.api data.split_file"
args_schema: dict[str, Any] = {
        "path": {"type": "string", "required": True},
        "chunk_mb": {"type": "string", "required": True},
        "output_dir": {"type": "string", "default": None},
}


def run(ctx):
    """Call ofx.api.data.split_file with the module's arguments."""
    from ofx.api.data import split_file as _func

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
