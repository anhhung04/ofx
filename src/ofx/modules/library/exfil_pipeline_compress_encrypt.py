"""Module wrapper for ``ofx.api.exfil.pipeline.compress_encrypt``."""

from __future__ import annotations

from typing import Any

name = "exfil.pipeline.compress_encrypt"
description = "Compress (zlib level 9) then XOR-encrypt *data* with *key*."
args_schema: dict[str, Any] = {
        "data": {"type": "string", "required": True},
        "key": {"type": "string", "required": True},
}


def run(ctx):
    """Call ofx.api.exfil.pipeline.compress_encrypt with the module's arguments."""
    from ofx.api.exfil.pipeline import compress_encrypt as _func

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
