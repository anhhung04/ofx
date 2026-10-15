"""Module wrapper for ``ofx.lib.ad.enum.ldap_query_command``."""

from __future__ import annotations

from typing import Any

name = "ad.enum.ldap_query_command"
description = "Build an ldapsearch command for AD enumeration."
args_schema: dict[str, Any] = {
        "dc_ip": {"type": "string", "required": True},
        "domain": {"type": "string", "required": True},
        "username": {"type": "string", "required": True},
        "password": {"type": "string", "required": True},
        "query": {"type": "string", "default": '(objectClass=user)'},
        "attributes": {"type": "string", "default": None},
        "base_dn": {"type": "string", "default": ''},
}


def run(ctx):
    """Call ofx.lib.ad.enum.ldap_query_command with the module's arguments."""
    from ofx.lib.ad.enum import ldap_query_command as _func

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
