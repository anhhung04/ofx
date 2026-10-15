"""Module wrapper for ``ofx.lib.ad.execution.pass_the_hash_command``."""

from __future__ import annotations

from typing import Any

name = "ad.execution.pass_the_hash_command"
description = "Build a Pass-the-Hash command using impacket."
args_schema: dict[str, Any] = {
        "target": {"type": "string", "required": True},
        "username": {"type": "string", "required": True},
        "nt_hash": {"type": "string", "required": True},
        "domain": {"type": "string", "default": '.'},
        "command": {"type": "string", "default": 'whoami /all'},
        "method": {"type": "string", "default": 'wmiexec'},
}


def run(ctx):
    """Call ofx.lib.ad.execution.pass_the_hash_command with the module's arguments."""
    from ofx.lib.ad.execution import pass_the_hash_command as _func

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
