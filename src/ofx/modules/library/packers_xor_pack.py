"""Module wrapper for ``ofx.lib.packers.xor_pack``."""

from __future__ import annotations

from typing import Any

name = "packers.xor_pack"
description = "XOR-pack data with a key. Returns base64-encoded packed data."
args_schema: dict[str, Any] = {
        'data': {'type': 'string', 'required': True, 'description': 'Data to pack (UTF-8 or base64)'},
        'key': {'type': 'string', 'required': True, 'description': 'XOR key'},
        'input_encoding': {'type': 'string', 'default': 'utf8', 'description': "'utf8' or 'base64'"},
}


def run(ctx):
    """Call ofx.lib.packers.xor_pack with the module's arguments."""
    from base64 import b64decode, b64encode

    from ofx.lib.packers import xor_pack as _func

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
    if kwargs.pop("input_encoding", "utf8") == "base64":
        data = b64decode(data)
    else:
        data = data.encode()
    result = _func(data, **kwargs)
    packed = b64encode(result).decode()
    ctx.add_outputs(result=packed)
    return packed
