"""Module wrapper for ``ofx.api.ad.kerberos.find_delegation_command``."""

from __future__ import annotations

from typing import Any

name = "ad.kerberos.find_delegation_command"
description = "Return commands to enumerate Kerberos delegation configurations."
args_schema: dict[str, Any] = {
        "domain": {"type": "string", "required": True},
        "username": {"type": "string", "required": True},
        "password": {"type": "string", "required": True},
        "dc_ip": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.api.ad.kerberos.find_delegation_command with the module's arguments."""
    from ofx.api.ad.kerberos import find_delegation_command as _func

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
        from ofx.modules.api import ApiModuleError

        raise ApiModuleError(
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
