"""Module wrapper for ``ofx.lib.credential_config.save_section_values``."""

from __future__ import annotations

from typing import Any

name = "credential_config.save_section_values"
description = "Persist non-empty credential values in an INI section."
args_schema: dict[str, Any] = {
        "path": {"type": "string", "required": True},
        "parser": {"type": "string", "required": True},
        "section": {"type": "string", "required": True},
        "values": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.lib.credential_config.save_section_values with the module's arguments."""
    from ofx.lib.credential_config import save_section_values as _func

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
