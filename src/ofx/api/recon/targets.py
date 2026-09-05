"""Target classification: distinguish domains, subdomains, CIDRs, IPs, and URLs."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

__all__ = [
    "classify_target",
    "split_targets",
    "TARGET_TYPES",
]

TARGET_TYPES = ("domain", "subdomain", "cidr", "ip", "url")

_HOST_RE = re.compile(r"^(?=.{1,253}$)[a-zA-Z0-9_]([a-zA-Z0-9_.-]*[a-zA-Z0-9])?$")

def classify_target(value: str) -> str:
    """Classify a single target string.

    Returns one of ``domain``, ``subdomain``, ``cidr``, ``ip``, or ``url``.
    Raises ``ValueError`` for values that match none of these.
    """
    v = value.strip()
    if not v:
        raise ValueError("empty target")

    if "://" in v:
        return "url"

    try:
        ipaddress.ip_address(v)
        return "ip"
    except ValueError:
        pass

    if "/" in v:
        try:
            ipaddress.ip_network(v, strict=False)
            return "cidr"
        except ValueError:
            pass

    host = v.split("/")[0].split(":")[0].rstrip(".")
    if not _HOST_RE.match(host) or "." not in host:
        raise ValueError(f"unrecognized target: {value!r}")

    # ponytail: naive 2-label check, use a PSL library if co.uk-style suffixes matter
    return "domain" if host.count(".") == 1 else "subdomain"

def split_targets(values: list[str]) -> dict[str, list[str]]:
    """Split target strings into a ``{type: [values]}`` dict.

    Unknown entries land under ``"unknown"``. All keys of
    :data:`TARGET_TYPES` are always present.
    """
    out: dict[str, list[str]] = {t: [] for t in TARGET_TYPES}
    out["unknown"] = []
    for value in values:
        v = value.strip()
        if not v:
            continue
        try:
            out[classify_target(v)].append(v)
        except ValueError:
            out["unknown"].append(v)
    return out
