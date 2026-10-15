"""Module wrapper for ``ofx.lib.c2.meterpreter_command``."""

from __future__ import annotations

from typing import Any

name = "c2.meterpreter_command"
description = "Build an msfvenom command to generate a Meterpreter payload."
args_schema: dict[str, Any] = {
        "lhost": {"type": "string", "required": True},
        "lport": {"type": "string", "required": True},
        "payload": {"type": "string", "default": 'linux/x64/meterpreter/reverse_tcp'},
        "output": {"type": "string", "default": 'payload.elf'},
        "format": {"type": "string", "default": 'elf'},
}


def run(ctx):
    """Call ofx.lib.c2.meterpreter_command with the module's arguments."""
    from ofx.lib.c2 import meterpreter_command as _func

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
