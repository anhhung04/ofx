"""Shared session-class accessors for the CLI command modules.

Both ``cloud.fleets`` and ``session.app`` expose module-level ``SessionManager`` /
``SessionStore`` globals as injection points (patched by tests or at runtime).
These helpers resolve a given override and fall back to the real
``ofx.cloud.sessions`` classes when the override is still ``None``.
"""

from __future__ import annotations


def _resolve_session_manager_cls(session_manager_cls=None):
    """Return the caller's SessionManager override, or the real class if unset."""
    if session_manager_cls is None:
        from ofx.cloud.sessions import SessionManager as session_manager_cls
    return session_manager_cls


def _resolve_session_store_cls(session_store_cls=None):
    """Return the caller's SessionStore override, or the real class if unset."""
    if session_store_cls is None:
        from ofx.cloud.sessions import SessionStore as session_store_cls
    return session_store_cls
