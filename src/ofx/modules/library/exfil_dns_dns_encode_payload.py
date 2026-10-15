"""Module wrapper for ``ofx.lib.exfil.dns.dns_encode_payload``."""

from __future__ import annotations

from typing import Any

name = "exfil.dns.dns_encode_payload"
description = "Encode bytes as a list of DNS label-safe base32 strings."
args_schema: dict[str, Any] = {
        "data": {"type": "string", "required": True},
        "label_max": {"type": "string", "default": 60},
}


def run(ctx):
    """Call ofx.lib.exfil.dns.dns_encode_payload with the module's arguments."""
    from ofx.lib.exfil.dns import dns_encode_payload as _func

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
