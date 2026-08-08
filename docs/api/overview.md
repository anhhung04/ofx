# API Overview

OFX exposes a broad Python API surface under `ofx.api.*` for automation workflows and scripts.

## Import convention

Use public imports like:

```python
from ofx.api.http import fetch, post
from ofx.api.file import read_file, write_file
```

## API groups

- **Reconnaissance**: search engines, DNS, service discovery, OOB helpers.
- **Exploitation**: HTTP client, shellcode, webshell, exploit connectors.
- **Post-exploitation**: remote execution helpers, file/network/utils, credentials.
- **OPSEC & evasion**: cleanup, timing/jitter, bypass helpers.
- **Privilege escalation & AD**: Linux/Windows checks and AD-oriented helpers.
- **Delivery & data**: payloads, bundle helpers, packers, exfil staging.

## Start with these pages

- [Reconnaissance](#)
- [Exploitation](#)
- [Post-Exploitation](post-#)
- [Evasion](evasion.md)
- [OPSEC](opsec.md)
- [Privesc](privesc.md)
- [Active Directory](ad.md)
- [Exfiltration](exfil.md)
- [Bundle](bundle.md)

## Example: HTTP + file APIs

```python
from ofx.api.http import fetch
from ofx.api.file import write_file

resp = fetch("https://example.com")
write_file("result.html", str(resp))
```

## Example: using APIs in workflow `script`

```yaml
jobs:
  enrich:
    steps:
      - script: |
          from ofx.api.http import fetch
          from ofx.api.file import write_file

          body = fetch("https://example.com")
          write_file(f"{{ ctx.output_path }}/page.txt", str(body))
```

## Discover APIs from CLI

```bash
ofx docs api --list
ofx docs api --module http
ofx docs api --module webshell
```

## Notes

- API availability can vary by installed extras.
- Use workflow templates and secret store for sensitive inputs.
