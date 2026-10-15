"""Module wrapper for ``ofx.lib.file.write_file``."""

from __future__ import annotations

from typing import Any

name = "file.write_file"
description = 'Write content to a file, creating parent directories if needed.'
args_schema: dict[str, Any] = {
        'content': {'type': 'string', 'required': True},
        'path': {'type': 'string', 'required': True},
}


def run(ctx):
    """Call ofx.lib.file.write_file with the module's arguments."""
    from ofx.lib.file import write_file as _func

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
