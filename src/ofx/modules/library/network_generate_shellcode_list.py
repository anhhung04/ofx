"""Module wrapper for ``ofx.lib.network.generate_shellcode_list``."""

from __future__ import annotations

from typing import Any

name = "network.generate_shellcode_list"
description = 'Get a list of shellcode payloads for specific architecture and platform.'
args_schema: dict[str, Any] = {
        'arch': {'type': 'string', 'default': 'x86'},
        'platform': {'type': 'string', 'default': 'linux'},
}


def run(ctx):
    """Call ofx.lib.network.generate_shellcode_list with the module's arguments."""
    from ofx.lib.network import generate_shellcode_list as _func

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
