# Data API

Helpers for staging and chunking data prior to exfil.

## Functions

- `archive_path(src, output=None, fmt="zip") -> Path`: Archive a directory or file (zip by default).
- `split_file(path, chunk_mb, output_dir=None) -> list[Path]`: Split a file into fixed-size chunks.

## Python Usage

```python
from ofx.api import data
archive = data.archive_path("/tmp/loot")
parts = data.split_file(archive, chunk_mb=50)
print(parts)
```

## Workflow Snippet

```yaml
steps:
  - name: archive loot
    run: |
      python - <<'PY'
      from ofx.api import data
      archive = data.archive_path("/tmp/loot")
      parts = data.split_file(archive, chunk_mb=50)
      print(parts)
      PY
```
