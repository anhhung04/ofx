"""Module wrapper for ``ofx.lib.packers.b64_gzip_unpack``."""

from __future__ import annotations

from typing import Any

name = "packers.b64_gzip_unpack"
description = 'Decode base64 + gzip-packed data. Returns UTF-8 text (or base64 if not decodable).'
args_schema: dict[str, Any] = {
        'data': {'type': 'string', 'required': True, 'description': 'Base64-encoded packed data'},
}


def run(ctx):
    """Call ofx.lib.packers.b64_gzip_unpack with the module's arguments."""
    from base64 import b64encode

    from ofx.lib.packers import b64_gzip_unpack as _func

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
    data = kwargs.pop("data")
    result = _func(data, **kwargs)
    try:
        unpacked = result.decode()
    except UnicodeDecodeError:
        unpacked = b64encode(result).decode()
    ctx.add_outputs(result=unpacked)
    return unpacked
