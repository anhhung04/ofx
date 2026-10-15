"""Traffic blending, User-Agent rotation, and domain fronting helpers."""

from __future__ import annotations

import random

__all__ = [
    "rotate_user_agent",
    "traffic_blend_headers",
    "domain_fronting_headers",
    "cdncheck_command",
]

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

def rotate_user_agent() -> str:
    """Return a random realistic browser User-Agent string."""
    return random.choice(_USER_AGENTS)

def traffic_blend_headers(referer: str = "https://www.google.com") -> dict[str, str]:
    """Return HTTP headers that blend C2/recon traffic with normal browser requests."""
    return {
        "User-Agent": rotate_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referer,
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
    }

def domain_fronting_headers(front_domain: str, real_host: str) -> dict[str, str]:
    """Return headers for HTTP domain fronting.

    The TLS SNI advertises *front_domain* (the CDN edge) while the HTTP
    ``Host`` header routes to *real_host* (the C2 backend).

    Note: To apply the SNI override in httpx use:
    ``client.get(url, extensions={"sni_hostname": front_domain})``.
    """
    return {
        "Host": real_host,
        "X-Forwarded-Host": real_host,
        "_front_domain": front_domain,
    }

def cdncheck_command(domain: str) -> str:
    """Return a shell command to detect whether *domain* is behind a CDN/WAF."""
    return (
        f"dig +short {domain} | head -3 | xargs -I{{}} whois {{}} 2>/dev/null "
        f"| grep -iE 'cloudflare|akamai|fastly|amazon|azure|incapsula|imperva|sucuri|zscaler'"
    )
