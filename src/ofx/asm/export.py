"""Convert OFX typed outputs to ASM assets and findings.

Maps the OFX ``OutputType`` taxonomy to ASM's asset/finding models
so scan results can be pushed to an ASM scope in a single call.
"""

from __future__ import annotations

import logging
from typing import Any

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

# OFX _type → ASM asset_type mapping
_TYPE_MAP: dict[str, str] = {
    "ip": "ip",
    "port": "service",
    "subdomain": "subdomain",
    "url": "url",
    "domain": "domain",
    "record": "domain",
    "certificate": "certificate",
    "tag": "tag",
    "exploit": "exploit",
    "user_account": "user_account",
}

# Types that become findings rather than assets
_FINDING_TYPES = {"vulnerability"}


def typed_output_to_asm_asset(
    item: dict[str, Any], source: str = "ofx"
) -> dict[str, str] | None:
    """Convert a single OFX typed output dict to an ASM generic import item.

    Returns ``{"type": ..., "value": ...}`` or ``None`` if unmappable.
    """
    otype = item.get("_type", "")

    if otype in _FINDING_TYPES:
        return None

    asset_type = _TYPE_MAP.get(otype)
    if not asset_type:
        return None

    value = _extract_value(item, otype)
    if not value:
        return None

    return {"type": asset_type, "value": value}


def typed_output_to_asm_finding(
    item: dict[str, Any], source: str = "ofx"
) -> dict[str, Any] | None:
    """Convert a vulnerability typed output to an ASM finding dict.

    Returns a dict compatible with the ASM generic import ``Finding`` shape,
    or ``None`` if the item is not a vulnerability.
    """
    otype = item.get("_type", "")
    if otype not in _FINDING_TYPES:
        return None

    severity = item.get("severity", "info")
    if severity == "unknown":
        severity = "info"

    return {
        "finding_type": item.get("matched_at", item.get("name", "unknown")),
        "severity": severity,
        "title": item.get("name", "") or item.get("matched_at", ""),
        "detail": {
            k: v
            for k, v in item.items()
            if k not in ("_type", "_uuid", "_target") and v
        },
        "source": source,
    }


def batch_convert(
    items: list[dict[str, Any]],
    source: str = "ofx",
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Convert a list of OFX typed outputs to ASM assets and findings.

    Returns ``(assets, findings)`` where each list contains dicts ready
    for the ASM import API.
    """
    assets: list[dict[str, str]] = []
    findings: list[dict[str, Any]] = []
    seen_assets: set[str] = set()

    for item in items:
        asset = typed_output_to_asm_asset(item, source=source)
        if asset:
            key = f"{asset['type']}:{asset['value']}"
            if key not in seen_assets:
                seen_assets.add(key)
                assets.append(asset)
            continue

        finding = typed_output_to_asm_finding(item, source=source)
        if finding:
            findings.append(finding)

    return assets, findings


def _extract_value(item: dict[str, Any], otype: str) -> str:
    """Extract the primary value string for the given output type."""
    if otype == "ip":
        return item.get("ip", "")
    if otype == "port":
        ip = item.get("ip", item.get("host", ""))
        port = item.get("port", "")
        if ip and port:
            return f"{ip}:{port}"
        return ""
    if otype == "subdomain":
        return item.get("host", "")
    if otype == "url":
        return item.get("url", "")
    if otype in ("domain", "record"):
        return item.get("host", item.get("name", ""))
    if otype == "certificate":
        return item.get("host", item.get("subject", ""))
    if otype == "tag":
        return item.get("name", "")
    if otype == "user_account":
        return item.get("username", "")
    return item.get("value", item.get("host", item.get("ip", "")))
