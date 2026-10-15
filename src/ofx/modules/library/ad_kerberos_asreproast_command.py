"""Module wrapper for ``ofx.lib.ad.kerberos.asreproast_command``."""

from __future__ import annotations

from typing import Any

name = "ad.kerberos.asreproast_command"
description = "Build an impacket GetNPUsers command for AS-REP Roasting."
args_schema: dict[str, Any] = {
        "domain": {"type": "string", "required": True},
        "dc_ip": {"type": "string", "required": True},
        "users_file": {"type": "string", "default": None},
        "username": {"type": "string", "default": ''},
        "password": {"type": "string", "default": ''},
        "output": {"type": "string", "default": 'hashes.asreproast'},
}


def run(ctx):
    """Call ofx.lib.ad.kerberos.asreproast_command with the module's arguments."""
    from ofx.lib.ad.kerberos import asreproast_command as _func

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
