"""Module wrapper for ``ofx.lib.packers.xor_unpack``."""

from __future__ import annotations

from typing import Any

name = "packers.xor_unpack"
description = "XOR-unpack base64-encoded data with a key. Returns UTF-8 text (or base64 if not decodable)."
args_schema: dict[str, Any] = {
        'data': {'type': 'string', 'required': True, 'description': 'Base64-encoded packed data'},
        'key': {'type': 'string', 'required': True, 'description': 'XOR key'},
}


def run(ctx):
    """Call ofx.lib.packers.xor_unpack with the module's arguments."""
    from base64 import b64decode, b64encode

    from ofx.lib.packers import xor_unpack as _func

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
    data = b64decode(kwargs.pop("data"))
    result = _func(data, **kwargs)
    try:
        unpacked = result.decode()
    except UnicodeDecodeError:
        unpacked = b64encode(result).decode()
    ctx.add_outputs(result=unpacked)
    return unpacked
