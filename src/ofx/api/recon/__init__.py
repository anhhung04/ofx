"""Extended reconnaissance helpers.

Submodules
----------
osint     -- email patterns, domain permutations, crt.sh, DNS helpers
portscan  -- async TCP connect scanner
web       -- HTTP tech fingerprinting and security header auditing
"""

from __future__ import annotations

from .osint import (
    asn_lookup_command,
    crtsh_subdomains,
    crtsh_subdomains_sync,
    domain_permutations,
    email_patterns,
    reverse_dns_command,
    whois_command,
    zone_transfer_command,
)
from .portscan import TOP_100_PORTS, PortResult, async_port_scan, port_scan
from .web import robots_txt_url, security_headers_audit, web_fingerprint

__all__ = [
    "email_patterns",
    "domain_permutations",
    "crtsh_subdomains",
    "crtsh_subdomains_sync",
    "asn_lookup_command",
    "whois_command",
    "reverse_dns_command",
    "zone_transfer_command",
    "TOP_100_PORTS",
    "PortResult",
    "async_port_scan",
    "port_scan",
    "web_fingerprint",
    "robots_txt_url",
    "security_headers_audit",
]
