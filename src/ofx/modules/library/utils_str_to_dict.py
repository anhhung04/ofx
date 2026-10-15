"""Module wrapper for ``ofx.lib.utils.str_to_dict``."""

from __future__ import annotations

from typing import Any

name = "utils.str_to_dict"
description = "Convert a string representation of a dictionary to an actual dict."
args_schema: dict[str, Any] = {
        "value": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.lib.utils.str_to_dict with the module's arguments."""
    from ofx.lib.utils import str_to_dict as _func

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
