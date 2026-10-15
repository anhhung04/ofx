"""Module wrapper for ``ofx.api.post.enum.bundled_tool_path``."""

from __future__ import annotations

from typing import Any

name = "post.enum.bundled_tool_path"
description = "Return the bundled tool path under the data directory."
args_schema: dict[str, Any] = {
        "filename": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.api.post.enum.bundled_tool_path with the module's arguments."""
    from ofx.api.post.enum import bundled_tool_path as _func

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
