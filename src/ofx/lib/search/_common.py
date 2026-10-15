"""Shared helpers for search engine clients."""

from __future__ import annotations


def is_ipv6_address_format(address: str) -> bool:
    """Return True if *address* looks like an IPv6 literal (has ``:``, no ``.``)."""
    return ":" in address and "." not in address
