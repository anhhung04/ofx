# Loot

Discover common loot artifacts and parse simple JSONL outputs.

## Functions

- `find_minidumps(root) -> list[Path]`: Recursively find `*.dmp` under `root`.
- `list_browser_profiles(root) -> list[Path]`: Locate common Chromium/Edge profile stores (Login Data, Cookies).
- `load_json_lines(path) -> list[dict]`: Load newline-delimited JSON with best-effort parsing.

## Python Usage

```python
from ofx.lib import loot
minidumps = loot.find_minidumps("/mnt/share")
profiles = loot.list_browser_profiles("/mnt/share")
```

## Workflow Snippet

```yaml
steps:
  - name: list loot
    module: python
    with:
      script: |
        from ofx.lib import loot
        print(loot.find_minidumps('/mnt/share'))
        print(loot.list_browser_profiles('/mnt/share'))
```
