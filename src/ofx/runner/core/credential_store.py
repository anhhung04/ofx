"""Credential storage utilities.

Centralises the ``should_store`` / ``store_from_typed_outputs`` logic
that was duplicated across ``CloudStepRunner``, ``TaskRunner``, and
``StepRunner``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from ofx.settings import settings

if TYPE_CHECKING:
    from pydantic import BaseModel

logger = logging.getLogger(settings.app_branding)


def should_store_creds(
    step_store_creds: bool | None,
    parent_model: BaseModel | None = None,
    global_default: bool | None = None,
) -> bool:
    """Determine whether to auto-store credentials from task outputs.

    Precedence: step-level ``store_creds`` ▸ job/workflow defaults
    ▸ global ``auto_store_creds`` setting.

    Args:
        step_store_creds: Explicit step-level toggle (``None`` = unset).
        parent_model: The parent job/workflow model (checked for
            ``defaults.store_creds``).
        global_default: Override for global setting (defaults to
            ``settings.auto_store_creds``).
    """
    if step_store_creds is not None:
        return step_store_creds

    if parent_model is not None:
        defaults = getattr(parent_model, "defaults", None)
        if defaults and getattr(defaults, "store_creds", False):
            return True

    if global_default is not None:
        return global_default
    return settings.auto_store_creds


def store_from_typed_outputs(
    typed_outputs: list[Any] | Sequence[Any],
    *,
    log_fn: Any | None = None,
) -> int:
    """Store ``UserAccount`` typed outputs in the credential DB.

    Returns the number of credentials successfully stored.
    Gracefully handles missing ``pykeepass`` or DB file.

    Args:
        typed_outputs: List of output-type objects (only ``UserAccount``
            instances are processed).
        log_fn: Callable ``(msg: str) -> None`` for debug logging.
            Falls back to module-level logger when ``None``.
    """
    from ofx.tasks.output_types import UserAccount

    _debug = log_fn or logger.debug

    accounts = [
        o for o in typed_outputs if isinstance(o, UserAccount) and o.username
    ]
    if not accounts:
        return 0

    try:
        from ofx.api.creds.exegol_history import ExegolHistoryDB

        db = ExegolHistoryDB()
    except (ImportError, FileNotFoundError) as e:
        _debug(f"Credential store unavailable: {e}")
        return 0

    stored = 0
    for account in accounts:
        try:
            cred = account.to_credential()
            existing = db.get_credential(cred.username)
            if (
                existing
                and existing.password == cred.password
                and existing.hash == cred.hash
                and existing.domain == cred.domain
            ):
                _debug(f"Credential already exists: {cred.username}")
                continue
            db.add_credential(
                username=cred.username,
                password=cred.password,
                hash_value=cred.hash,
                domain=cred.domain,
                comment=cred.comment,
            )
            stored += 1
        except Exception as e:
            _debug(f"Failed to store credential for {account.username}: {e}")

    return stored
