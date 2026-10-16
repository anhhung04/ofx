"""Module wrapper for ``ofx.lib.recon.osint.email_patterns``."""

from __future__ import annotations

from typing import Any

name = "recon.osint.email_patterns"
description = "Generate common corporate email address patterns for a person."
args_schema: dict[str, Any] = {
        "first": {"type": "string", "required": True},
        "last": {"type": "string", "required": True},
        "domain": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.lib.recon.osint.email_patterns with the module's arguments."""
    from ofx.lib.recon.osint import email_patterns as _func

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
