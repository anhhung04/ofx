"""Credential storage helpers for runner services."""

from __future__ import annotations

import logging
from typing import Any

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


def should_store_creds(
    step_store_creds: bool | None,
    parent_model: Any | None = None,
    global_default: bool | None = None,
) -> bool:
    """Determine whether typed credential outputs should be stored."""

    if step_store_creds is not None:
        return step_store_creds

    defaults = getattr(parent_model, "defaults", None) if parent_model is not None else None
    if defaults and getattr(defaults, "store_creds", False):
        return True

    if global_default is not None:
        return global_default
    return settings.auto_store_creds


def store_and_log_typed_outputs(
    typed_outputs: list[Any],
    *,
    debug_fn: Any | None = None,
    info_fn: Any | None = None,
) -> None:
    """Log typed outputs (credential store disabled)."""
    debug = debug_fn or logger.debug
    if not typed_outputs:
        debug("No typed outputs to store")
        return
    debug(f"Typed outputs: {len(typed_outputs)} items (credential store disabled)")


__all__ = [
    "should_store_creds",
    "store_and_log_typed_outputs",
]
