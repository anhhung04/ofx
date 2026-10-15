"""Proxy configuration and routing helpers."""

from __future__ import annotations

from typing import Any

__all__ = [
    "build_proxychains_conf",
    "http_proxy_env",
]

def build_proxychains_conf(
    proxies: list[dict[str, Any]],
    *,
    chain_type: str = "dynamic_chain",
    proxy_dns: bool = True,
) -> str:
    """Build a proxychains4.conf content string.

    Args:
        proxies: List of proxy dicts. Each must have ``type``
            (``socks5`` / ``socks4`` / ``http``), ``host``, and ``port``.
            Optional ``user`` and ``pass`` keys for authenticated proxies.
        chain_type: ``dynamic_chain`` | ``strict_chain`` |
            ``round_robin_chain`` | ``random_chain``.
        proxy_dns: Route DNS queries through the proxy chain.
    """
    lines = [chain_type, ""]
    if proxy_dns:
        lines += ["proxy_dns", ""]
    lines.append("[ProxyList]")
    for p in proxies:
        entry = f"{p['type']} {p['host']} {p['port']}"
        if p.get("user") and p.get("pass"):
            entry += f" {p['user']} {p['pass']}"
        lines.append(entry)
    return "\n".join(lines)

def http_proxy_env(
    host: str,
    port: int,
    *,
    scheme: str = "socks5",
    user: str = "",
    password: str = "",
) -> dict[str, str]:
    """Return an env vars dict to route HTTP/HTTPS through a proxy.

    Suitable for a step's ``env`` block or direct ``os.environ`` injection.
    """
    creds = f"{user}:{password}@" if user else ""
    proxy_url = f"{scheme}://{creds}{host}:{port}"
    return {
        "http_proxy": proxy_url,
        "https_proxy": proxy_url,
        "HTTP_PROXY": proxy_url,
        "HTTPS_PROXY": proxy_url,
        "ALL_PROXY": proxy_url,
    }
