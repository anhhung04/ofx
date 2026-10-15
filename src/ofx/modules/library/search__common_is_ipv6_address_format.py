"""Module wrapper for ``ofx.api.search._common.is_ipv6_address_format``."""

from __future__ import annotations

from typing import Any

name = "search._common.is_ipv6_address_format"
description = "Return True if *address* looks like an IPv6 literal (has ``:``, no ``.``)."
args_schema: dict[str, Any] = {
        "address": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.api.search._common.is_ipv6_address_format with the module's arguments."""
    from ofx.api.search._common import is_ipv6_address_format as _func

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
