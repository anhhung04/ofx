# Recon API

The `ofx.api.recon` module provides active and passive reconnaissance helpers: async TCP port scanning, OSINT data gathering, and web fingerprinting.

!!! note
    For internet-wide asset discovery using search engines (Shodan, FOFA, ZoomEye), see the [Reconnaissance APIs](#) section.

---

## Submodules

| Submodule | Purpose |
|-----------|---------|
| `recon.portscan` | Async TCP port scanner |
| `recon.osint` | OSINT: crt.sh, WHOIS, email patterns, ASN |
| `recon.web` | Web fingerprinting and header auditing |

---

## Port Scanning (`recon.portscan`)

### `async_port_scan(host, ports, *, timeout=1.0, concurrency=200) -> list[PortResult]`

Async TCP connect scan. Scan up to `concurrency` ports in parallel.

### `port_scan(host, ports, *, timeout=1.0, concurrency=200) -> list[PortResult]`

Synchronous wrapper around `async_port_scan` (runs a new event loop).

### `TOP_100_PORTS`

`list[int]` of the 100 most commonly open TCP ports.

### `PortResult`

Named dataclass: `host: str`, `port: int`, `open: bool`, `banner: str | None`.

```python
from ofx.api.recon import port_scan, TOP_100_PORTS

results = port_scan("10.0.0.5", TOP_100_PORTS, timeout=0.5)
for r in results:
    if r.open:
        print(f"{r.port}/tcp  open  {r.banner or ''}")
```

---

## OSINT (`recon.osint`)

### `crtsh_subdomains(domain) -> Coroutine[set[str]]`

Async: query crt.sh certificate transparency logs and return discovered subdomains.

### `crtsh_subdomains_sync(domain) -> set[str]`

Synchronous wrapper.

### `email_patterns(first, last, domain) -> list[str]`

Generate common corporate email permutations (`first.last@domain`, `flast@domain`, etc.).

### `domain_permutations(domain) -> list[str]`

Generate typo-squatting and look-alike domain permutations.

### `asn_lookup_command(ip) -> str`
### `whois_command(target) -> str`
### `reverse_dns_command(ip) -> str`
### `zone_transfer_command(domain, nameserver) -> str`

Return shell command strings for ASN lookup, WHOIS, PTR records, and DNS zone transfer attempts.

```python
from ofx.api.recon import crtsh_subdomains_sync, email_patterns

subs = crtsh_subdomains_sync("target.corp")
print(f"Found {len(subs)} subdomains via crt.sh")

emails = email_patterns("john", "doe", "target.corp")
print(emails)
```

---

## Web Fingerprinting (`recon.web`)

### `web_fingerprint(url, *, timeout=5) -> dict`

Return a dict with `server`, `powered_by`, `title`, `status_code`, and raw `headers` extracted from a GET request.

### `robots_txt_url(base_url) -> str`

Return the URL of the `robots.txt` file for a given base URL.

### `security_headers_audit(headers) -> dict[str, str]`

Given a response headers dict, return a report of missing or misconfigured security headers (`Strict-Transport-Security`, `Content-Security-Policy`, `X-Frame-Options`, etc.).

```python
from ofx.api.recon import web_fingerprint, security_headers_audit

info = web_fingerprint("https://target.com")
print(f"Server: {info['server']}  Title: {info['title']}")

audit = security_headers_audit(info["headers"])
for header, finding in audit.items():
    print(f"  {header}: {finding}")
```

---

## Workflow Snippet

```yaml
jobs:
  recon:
    steps:
      - name: port scan
        script: |
          from ofx.api.recon import port_scan, TOP_100_PORTS
          results = port_scan("{{ inputs.target }}", TOP_100_PORTS)
          for r in results:
              if r.open:
                  print(f"{r.port}/tcp open")
```

---

## See Also

- [Reconnaissance APIs](#) — Shodan, FOFA, ZoomEye, OOB testing
- [AD API](ad.md) — Active Directory enumeration
