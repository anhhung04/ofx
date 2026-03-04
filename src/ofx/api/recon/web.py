"""Web fingerprinting and HTTP security header auditing."""

from __future__ import annotations

__all__ = [
    "web_fingerprint",
    "robots_txt_url",
    "security_headers_audit",
]

_TECH_PATTERNS: list[tuple[str, str, str]] = [
    ("framework", "asp.net", "ASP.NET"),
    ("language", "php", "PHP"),
    ("framework", "express", "Express.js"),
    ("framework", "laravel", "Laravel"),
    ("framework", "django", "Django"),
    ("framework", "rails", "Ruby on Rails"),
    ("web_server", "nginx", "nginx"),
    ("web_server", "apache", "Apache"),
    ("web_server", "iis", "IIS"),
    ("web_server", "litespeed", "LiteSpeed"),
    ("web_server", "tomcat", "Tomcat"),
]

_WAF_SIGNALS: dict[str, str] = {
    "cf-ray": "Cloudflare",
    "x-sucuri-id": "Sucuri",
    "x-fw-hash": "Fortinet",
    "x-iinfo": "Incapsula",
    "x-amz-cf-id": "AWS CloudFront",
    "x-azure-ref": "Azure CDN",
    "x-cdn": "CDN",
    "x-waf-event-info": "WAF",
}

_SECURITY_HEADERS: list[str] = [
    "strict-transport-security",
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
    "x-xss-protection",
    "cross-origin-opener-policy",
    "cross-origin-resource-policy",
]


def web_fingerprint(headers: dict[str, str]) -> dict[str, str]:
    """Detect web technologies from HTTP response headers.

    Returns a ``{category: detected_value}`` dict. Categories include
    ``server``, ``x-powered-by``, ``framework``, ``language``,
    ``web_server``, and ``waf_cdn``.
    """
    findings: dict[str, str] = {}
    lh = {k.lower(): v for k, v in headers.items()}

    if (server := lh.get("server", "")):
        findings["server"] = server
    if (pb := lh.get("x-powered-by", "")):
        findings["x-powered-by"] = pb

    combined = " ".join(lh.values()).lower()
    for category, pattern, label in _TECH_PATTERNS:
        if pattern in combined:
            findings.setdefault(category, label)

    for header, tech in _WAF_SIGNALS.items():
        if header in lh:
            findings.setdefault("waf_cdn", tech)

    return findings


def robots_txt_url(base_url: str) -> str:
    """Return the ``robots.txt`` URL for *base_url*."""
    return base_url.rstrip("/") + "/robots.txt"


def security_headers_audit(headers: dict[str, str]) -> dict[str, str]:
    """Evaluate the presence of HTTP security headers.

    Returns ``{header_name: header_value_or_"MISSING"}``.
    """
    lh = {k.lower(): v for k, v in headers.items()}
    return {h: lh.get(h, "MISSING") for h in _SECURITY_HEADERS}
