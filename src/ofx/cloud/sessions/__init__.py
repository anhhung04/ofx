"""Detached session management for OFX cloud and local jobs.

Sessions allow fire-and-forget workflow execution — submit a job, disconnect,
and come back later to check status, fetch results, and optionally encrypt them.

Usage:
    from ofx.cloud.sessions import SessionManager, SessionStore, Session

    manager = SessionManager()
    session = await manager.submit("scan.yml", "recon", target="local")
    await manager.status(session.id)
    await manager.fetch(session.id, passphrase="secret")
"""

from ofx.cloud.sessions.manager import SessionManager
from ofx.cloud.sessions.models import Session, SessionStatus, SessionTarget
from ofx.cloud.sessions.store import SessionStore

__all__ = [
    "Session",
    "SessionStatus",
    "SessionTarget",
    "SessionStore",
    "SessionManager",
]
