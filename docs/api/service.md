# Service API

Grab lightweight banners and hint protocols during recon.

## Functions

- `scan_banner(host, port, timeout=3.0, tls=None, max_bytes=1024) -> ServiceInfo`: Connect, optionally wrap in TLS, read up to `max_bytes`, and return `ServiceInfo(host, port, banner, tls, protocol_guess)`.
- `detect_protocol(port, banner=None) -> str | None`: Heuristic protocol guess used by `scan_banner`.

## Python Usage

```python
from ofx.api import service
info = service.scan_banner("10.0.0.5", 8443, tls=True)
print(info)
```

## Workflow Snippet

```yaml
steps:
  - name: banner grab 8443
    run: |
      python - <<'PY'
      from ofx.api import service
      info = service.scan_banner("10.0.0.5", 8443, tls=True)
      print(info)
      PY
```
