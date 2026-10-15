# Packers API

Simple packing/obfuscation helpers for transport.

## Functions

- `xor_pack(data: bytes, key) -> bytes` / `xor_unpack(data, key) -> bytes`: XOR with repeating key.
- `gzip_pack(data: bytes) -> bytes` / `gzip_unpack(data) -> bytes`: Gzip compress/decompress.
- `b64_gzip_pack(data: bytes) -> str` / `b64_gzip_unpack(data: str) -> bytes`: Gzip then base64 (and reverse).

## Python Usage

```python
from ofx.lib import packers
packed = packers.b64_gzip_pack(b"secret")
raw = packers.b64_gzip_unpack(packed)
```

## Workflow Snippet

```yaml
steps:
  - name: pack payload
    module: python
    with:
      script: |
        from ofx.lib import packers
        data = b"SECRET"
        encoded = packers.b64_gzip_pack(data)
        print(encoded)
        restored = packers.b64_gzip_unpack(encoded)
        print(restored)
```
