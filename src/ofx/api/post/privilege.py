"""Privilege detection helpers."""

from __future__ import annotations

import re

__all__ = ["is_admin_from_whoami", "is_root_from_id"]

def is_root_from_id(id_output: str) -> bool:
    """Detect root privileges from `id` output (uid=0)."""
    return "uid=0" in (id_output or "")

def is_admin_from_whoami(whoami_output: str) -> bool:
    """Detect Windows admin privileges from whoami output.

    Checks common elevated identities such as NT AUTHORITY\\SYSTEM.
    """
    value = (whoami_output or "").lower()
    if "nt authority\\system" in value:
        return True
    if re.search(r"\\administrator$", value):
        return True
    if "admin" == value.strip():
        return True
    return False
