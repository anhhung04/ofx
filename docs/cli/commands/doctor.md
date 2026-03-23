# Doctor Command

`ofx doctor` provides reliability diagnostics for operational readiness.

## Usage

```bash
ofx doctor fleet [OPTIONS]
```

## `doctor fleet`

Run a fleet reliability scorecard against a cloud profile.

### What it checks

- Cloud provider registration
- Provider-specific auth/config requirements
  - DigitalOcean token presence
  - AWS credentials (explicit or ambient/IAM warning)
  - Static host/hosts presence
- Connection auth readiness
  - SSH key/password checks for Linux
  - WinRM credential checks for Windows
- Optional live probes:
  - Network connectivity
  - Authenticated login

### Options

| Option | Description |
|---|---|
| `--profile, -p` | Cloud profile name to score (uses default profile if omitted) |
| `--host` | Optional host override for live probe |
| `--check-connectivity` | Enable live connectivity + login probes |
| `--timeout, -t` | Probe timeout in seconds (default: `60`) |

### Examples

```bash
# Score default cloud profile
ofx doctor fleet

# Score an explicit profile
ofx doctor fleet --profile do-small

# Include live connectivity/login checks
ofx doctor fleet --profile static-lab --check-connectivity --host 10.10.10.5
```

### Exit codes

- `0`: No failing checks
- `1`: One or more failing checks

Warnings are informational and do not fail the command.
