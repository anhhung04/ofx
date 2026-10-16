"""Module wrapper for ``ofx.lib.privesc.windows.juicy_potato_command``."""

from __future__ import annotations

from typing import Any

name = "privesc.windows.juicy_potato_command"
description = "Return a JuicyPotato command to abuse SeImpersonatePrivilege."
args_schema: dict[str, Any] = {
        "payload": {"type": "string", "default": 'cmd.exe'},
        "clsid": {"type": "string", "default": '{9B1F122C-2982-4e91-AA8B-E071D54F2A4D}'},
        "port": {"type": "string", "default": 10000},
}


def run(ctx):
    """Call ofx.lib.privesc.windows.juicy_potato_command with the module's arguments."""
    from ofx.lib.privesc.windows import juicy_potato_command as _func

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
