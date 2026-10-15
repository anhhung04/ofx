"""Module wrapper for ``ofx.lib.credential_config.load_section_values``."""

from __future__ import annotations

from typing import Any

name = "credential_config.load_section_values"
description = "Load selected values from an INI section."
args_schema: dict[str, Any] = {
        "path": {"type": "string", "required": True},
        "section": {"type": "string", "required": True},
        "keys": {"type": "string", "required": True},
        "logger": {"type": "string", "default": None},
}


def run(ctx):
    """Call ofx.lib.credential_config.load_section_values with the module's arguments."""
    from ofx.lib.credential_config import load_section_values as _func

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
