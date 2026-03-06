# API CLI Reference

This page documents the CLI commands for interacting with OFX APIs.

## Usage

```bash
ofx api <command> [options]
```

## Commands

| Command | Description |
|---------|-------------|
| `ofx api recon` | Run reconnaissance APIs |
| `ofx api exploit` | Run exploitation APIs |
| `ofx api post` | Run post-exploitation APIs |
| `ofx api evasion` | Run evasion APIs |
| `ofx api exfil` | Run exfiltration APIs |
| `ofx api lateral` | Run lateral movement APIs |
| `ofx api persistence` | Run persistence APIs |
| `ofx api payloads` | Run payload generation APIs |
| `ofx api service` | Run service enumeration APIs |

## Examples

```bash
ofx api recon --target example.com
ofx api exploit --module ms17_010 --target 192.168.1.10
```

---

[← Back to API Reference](../../reference/api.md)
