"""Credential storage helpers for runner services."""

from __future__ import annotations

import logging
from collections.abc import Sequence
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
    """Store [`UserAccount`](src/ofx/tasks/output_types.py:1) outputs in the credential DB."""

    from ofx.tasks.output_types import UserAccount

    debug = log_fn or logger.debug
    accounts = [item for item in typed_outputs if isinstance(item, UserAccount) and item.username]
    if not accounts:
        return 0

    try:
        from ofx.api.creds.exegol_history import ExegolHistoryDB

        db = ExegolHistoryDB()
    except (ImportError, FileNotFoundError) as exc:
        debug(f"Credential store unavailable: {exc}")
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
                debug(f"Credential already exists: {cred.username}")
                continue
            db.add_credential(
                username=cred.username,
                password=cred.password,
                hash_value=cred.hash,
                domain=cred.domain,
                comment=cred.comment,
            )
            stored += 1
        except Exception as exc:
            debug(f"Failed to store credential for {account.username}: {exc}")

    return stored


__all__ = ["should_store_creds", "store_from_typed_outputs"]
