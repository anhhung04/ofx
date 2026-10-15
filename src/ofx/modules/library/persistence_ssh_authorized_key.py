"""Module wrapper for ``ofx.lib.persistence.ssh_authorized_key``."""

from __future__ import annotations

from typing import Any

name = "persistence.ssh_authorized_key"
description = "Return commands to install an SSH public key for passwordless access."
args_schema: dict[str, Any] = {
        "public_key": {"type": "string", "required": True},
        "user_home": {"type": "string", "default": '~'},
}


def run(ctx):
    """Call ofx.lib.persistence.ssh_authorized_key with the module's arguments."""
    from ofx.lib.persistence import ssh_authorized_key as _func

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
