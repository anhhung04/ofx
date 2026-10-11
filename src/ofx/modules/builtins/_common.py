"""Shared helpers for the pure-Python builtin modules.

Each builtin receives a :class:`~ofx.modules.base.ModuleContext` whose
``args``/``inputs`` carry the merged workflow inputs plus the step's ``with:``
block, and whose ``env`` holds the per-run environment (``OFX_RUN_DIR``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ofx.modules.base import ModuleContext

NO_RUN_DIR_MESSAGE = "OFX_RUN_DIR is not set; cannot locate run artifacts"


def arg(ctx: ModuleContext, key: str) -> Any:
    """Return a module argument from ``ctx.args`` (falling back to ``ctx.inputs``).

    Both are populated with the same merged arguments by the module runner;
    the fallback keeps direct invocations working when only one is set.
    """
    if key in ctx.args:
        return ctx.args[key]
    return ctx.inputs.get(key)


def text_arg(ctx: ModuleContext, key: str) -> str:
    """Return a module argument as a stripped string (``""`` when unset)."""
    value = arg(ctx, key)
    return "" if value is None else str(value).strip()


def run_dir(ctx: ModuleContext, override: str = "") -> Path:
    """Return the artifact directory: explicit override, then ``OFX_RUN_DIR``.

    ``ctx.env`` (the run's environment) wins over the process environment so a
    stale exported ``OFX_RUN_DIR`` can never redirect artifacts.
    """
    candidate = (
        override
        or str(ctx.env.get("OFX_RUN_DIR") or "")
        or os.environ.get("OFX_RUN_DIR", "")
    )
    if not candidate:
        raise RuntimeError(NO_RUN_DIR_MESSAGE)
    return Path(candidate).expanduser()


__all__ = ["NO_RUN_DIR_MESSAGE", "arg", "run_dir", "text_arg"]
