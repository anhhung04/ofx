"""Module wrapper for ``ofx.lib.ad.enum.bloodhound_collection_command``."""

from __future__ import annotations

from typing import Any

name = "ad.enum.bloodhound_collection_command"
description = "Build a SharpHound (BloodHound CE) ingestor command."
args_schema: dict[str, Any] = {
        "domain": {"type": "string", "required": True},
        "username": {"type": "string", "required": True},
        "password": {"type": "string", "required": True},
        "dc": {"type": "string", "required": True},
        "collection_method": {"type": "string", "default": 'All'},
        "stealth": {"type": "string", "default": False},
        "zip_filename": {"type": "string", "default": 'loot.zip'},
}


def run(ctx):
    """Call ofx.lib.ad.enum.bloodhound_collection_command with the module's arguments."""
    from ofx.lib.ad.enum import bloodhound_collection_command as _func

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
