"""OSINT helpers: email patterns, domain permutations, certificate transparency."""

from __future__ import annotations

import asyncio
import logging
import re

__all__ = [
    "email_patterns",
    "domain_permutations",
    "crtsh_subdomains",
    "crtsh_subdomains_sync",
    "asn_lookup_command",
    "whois_command",
    "reverse_dns_command",
    "zone_transfer_command",
]


def email_patterns(first: str, last: str, domain: str) -> list[str]:
    """Generate common corporate email address patterns for a person.

    Args:
        first: First name.
        last: Last name.
        domain: Email domain (e.g. ``example.com``).
    """
    f, last_name = first.lower().strip(), last.lower().strip()
    fi, li = f[0], last_name[0]
    patterns = [
        f"{f}@{domain}",
        f"{last_name}@{domain}",
        f"{f}.{last_name}@{domain}",
        f"{f}{last_name}@{domain}",
        f"{fi}{last_name}@{domain}",
        f"{f}{li}@{domain}",
        f"{fi}.{last_name}@{domain}",
        f"{last_name}.{f}@{domain}",
        f"{last_name}{fi}@{domain}",
        f"{f}_{last_name}@{domain}",
        f"{fi}_{last_name}@{domain}",
    ]
    return list(dict.fromkeys(patterns))


def domain_permutations(domain: str) -> list[str]:
    """Return typosquatting and lookalike domain permutations.

    Covers: character omission/doubling, TLD swaps, common prefix subdomains,
    and basic homoglyph substitutions.
    """
    if "." not in domain:
        return []
    name, tld = domain.rsplit(".", 1)
    perms: list[str] = []

    for i in range(len(name)):
        perms.append(name[:i] + name[i + 1 :] + f".{tld}")
        perms.append(name[:i] + name[i] * 2 + name[i + 1 :] + f".{tld}")

    for alt in ("com", "net", "org", "io", "co", "info", "biz", "us", "uk"):
        if alt != tld:
            perms.append(f"{name}.{alt}")

    for prefix in (
        "www",
        "mail",
        "remote",
        "vpn",
        "portal",
        "login",
        "dev",
        "staging",
        "api",
        "admin",
    ):
        perms.append(f"{prefix}-{name}.{tld}")
        perms.append(f"{prefix}.{name}.{tld}")

    homoglyphs: dict[str, list[str]] = {
        "a": ["4", "@"],
        "e": ["3"],
        "i": ["1", "l"],
        "o": ["0"],
        "s": ["5"],
        "l": ["1", "i"],
    }
    for char, replacements in homoglyphs.items():
        if char in name:
            for rep in replacements:
                perms.append(name.replace(char, rep, 1) + f".{tld}")

    return list(dict.fromkeys(p for p in perms if p and "." in p))


async def crtsh_subdomains(domain: str, *, timeout: float = 15.0) -> list[str]:
    """Query crt.sh certificate transparency logs for subdomains of *domain*.

    Returns a sorted, deduplicated list. Requires ``httpx``.
    """
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                "https://crt.sh/",
                params={"q": f"%.{domain}", "output": "json"},
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            names: set[str] = set()
            for entry in resp.json():
                for name in re.split(r"[\n,]", entry.get("name_value", "")):
                    name = name.strip().lstrip("*.")
                    if name.endswith(f".{domain}") or name == domain:
                        names.add(name.lower())
            return sorted(names)
    except Exception:
        logging.getLogger(__name__).debug(
            "crtsh subdomain lookup failed for %s", domain
        )
        return []


def crtsh_subdomains_sync(domain: str, *, timeout: float = 15.0) -> list[str]:
    """Synchronous wrapper around :func:`crtsh_subdomains`."""
    return asyncio.run(crtsh_subdomains(domain, timeout=timeout))


def asn_lookup_command(ip: str) -> str:
    """Return a shell command to look up the ASN/org for *ip* via Team Cymru whois."""
    return f"whois -h whois.cymru.com ' -v {ip}'"


def whois_command(target: str) -> str:
    """Return a whois command for a domain or IP address."""
    return f"whois {target}"


def reverse_dns_command(ip: str) -> str:
    """Return a dig command for a reverse DNS lookup."""
    return f"dig +short -x {ip}"


def zone_transfer_command(domain: str, nameserver: str = "") -> str:
    """Return a dig AXFR command attempting a DNS zone transfer.

    Args:
        nameserver: Specific NS to query. Derived from SOA if not provided.
    """
    ns = nameserver or f"$(dig +short NS {domain} | head -1)"
    return f"dig axfr {domain} @{ns}"
