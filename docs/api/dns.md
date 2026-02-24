# DNS API

Lightweight DNS helpers for quick recon and callback prep.

## Functions

- `resolve_host(host, timeout=2.0) -> list[str]`: Async resolve of all A/AAAA records.
- `resolve_host_sync(host, timeout=2.0) -> list[str]`: Sync resolver convenience.
- `bruteforce_subdomains(domain, candidates, concurrency=100, timeout=2.0, jitter=0.0) -> list[tuple[str,str]]`: Async subdomain bruteforce using system DNS.
- `bruteforce_subdomains_sync(...)`: Sync wrapper.

## Python Usage

```python
from ofx.api import dns
ips = await dns.resolve_host("portal.corp.local")
hits = await dns.bruteforce_subdomains("corp.local", ["vpn", "mail"], concurrency=50)
```

## Workflow Snippet

```yaml
steps:
  - name: dns bruteforce
    run: |
      python - <<'PY'
      from ofx.api import dns
      hits = dns.bruteforce_subdomains_sync(
          "corp.local",
          ["vpn", "mail", "git"],
          concurrency=50,
          jitter=0.05,
      )
      print(hits)
      PY
```
