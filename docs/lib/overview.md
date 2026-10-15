# Library Overview

OFX exposes a broad Python library under `ofx.lib.*` for automation workflows and scripts. Every public function is also callable as a workflow module (`module: local.builtin.<dotted.path>`).

## Import convention

Use public imports like:

```python
from ofx.lib.http import fetch, post
from ofx.lib.file import read_file, write_file
```

## API groups

- **Reconnaissance**: search engines, DNS, service discovery, OOB helpers.
- **Exploitation**: HTTP client, shellcode, webshell, exploit connectors.
- **Post-exploitation**: remote execution helpers, file/network/utils, credentials.
- **OPSEC & evasion**: cleanup, timing/jitter, bypass helpers.
- **Privilege escalation & AD**: Linux/Windows checks and AD-oriented helpers.
- **Delivery & data**: payloads, bundle helpers, packers, exfil staging.

## Start with these pages

- [Reconnaissance](recon.md)
- [Post-Exploitation / Persistence](persistence.md) — the `ofx.lib.post` runners and persistence helpers
- [Evasion](evasion.md)
- [OPSEC](opsec.md)
- [Privesc](privesc.md)
- [Active Directory](ad.md)
- [Exfiltration](exfil.md)
- [Bundle](bundle.md)

## Example: HTTP + file APIs

```python
from ofx.lib.http import fetch
from ofx.lib.file import write_file

resp = fetch("https://example.com")
write_file("result.html", str(resp))
```

## Example: using APIs in a `module: python` step

```yaml
jobs:
  enrich:
    steps:
      - module: python
        with:
          script: |
            from ofx.lib.http import fetch
            from ofx.lib.file import write_file

            body = fetch("https://example.com")
            write_file(f"{{ ctx.output_path }}/page.txt", str(body))
```

## Discover APIs from CLI

```bash
ofx api --list
ofx api --module http
ofx api --module webshell
```

List callable workflow modules (including every `ofx.lib` function wrapped as a
library module):

```bash
ofx flow modules list
ofx flow modules info http.fetch
```

## Notes

- API availability can vary by installed extras.
- Use workflow templates and secret store for sensitive inputs.
