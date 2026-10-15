"""Module wrapper for ``ofx.lib.bundle.deliverer.make_adapter``."""

from __future__ import annotations

from typing import Any

name = "bundle.deliverer.make_adapter"
description = "Instantiate the appropriate delivery adapter."
args_schema: dict[str, Any] = {
        "runner": {"type": "string", "required": True},
        "method": {"type": "string", "default": 'auto'},
        "remote_tmp": {"type": "string", "default": '/tmp/ofx_runner.py'},
        "python": {"type": "string", "default": None},
        "windows": {"type": "string", "default": False},
        "http_host": {"type": "string", "default": '0.0.0.0'},
        "http_port": {"type": "string", "default": 8888},
        "http_route": {"type": "string", "default": '/run'},
}


def run(ctx):
    """Call ofx.lib.bundle.deliverer.make_adapter with the module's arguments."""
    from ofx.lib.bundle.deliverer import make_adapter as _func

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
