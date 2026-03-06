# Cloud Configuration

This page covers how cloud config is resolved, profile merging, provider authentication, and connection settings.

## Config Resolution Order

When a job has a `cloud:` field, OFX resolves the final configuration by merging multiple layers:

```
cloud profile (from ~/.ofx/cloud.yml)
  ↓  merged with
inline overrides (from workflow YAML)
  ↓  merged with
CLI overrides (--cloud-profile flag)
  =
final CloudConfig used for provisioning
```

### String shorthand

A bare string references a named profile:

```yaml
jobs:
  scan:
    cloud: do-small   # Equivalent to cloud: { profile: do-small }
```

### Inline with profile base

Inline fields override the profile:

```yaml
jobs:
  scan:
    cloud:
      profile: do-small      # Load base config
      size: s-4vcpu-8gb      # Override just the size
      region: sgp1            # Override region
```

### Fully inline

No profile needed — everything specified directly:

```yaml
jobs:
  scan:
    cloud:
      provider: digitalocean
      region: lon1
      size: s-2vcpu-4gb
      image: ubuntu-24-04-x64
      ssh_user: root
      ssh_key: ~/.ssh/id_rsa
```

## Provider Authentication

### DigitalOcean

The token is resolved in priority order:

| Priority | Source | Example |
|----------|--------|---------|
| 1 | `extra.token` in profile/inline config | `extra: { token: "dop_v1_..." }` |
| 2 | `DIGITALOCEAN_TOKEN` environment variable | `export DIGITALOCEAN_TOKEN=dop_v1_...` |
| 3 | OFX secret named `digitalocean_token` | `ofx secret set digitalocean_token=dop_v1_...` |

Using the OFX secret store is recommended — it's encrypted at rest and automatically loaded:

```bash
ofx secret set digitalocean_token=dop_v1_abcdef123456
```

### AWS EC2

Uses the standard boto3 credential chain:

| Priority | Source |
|----------|--------|
| 1 | `extra.aws_access_key_id` / `extra.aws_secret_access_key` in config |
| 2 | `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` env vars |
| 3 | `~/.aws/credentials` file |
| 4 | IAM instance profile (when running on EC2) |

### Static Provider

No authentication to a cloud API. Only SSH/WinRM credentials are needed:

```yaml
cloud:
  provider: static
  host: 192.168.1.100
  ssh_user: root
  ssh_key: ~/.ssh/lab_key
```

## Connection Settings

### SSH (default)

| Field | Default | Description |
|-------|---------|-------------|
| `ssh_user` | `root` | SSH username |
| `ssh_key` | `""` | Path to private key file |
| `ssh_password` | `""` | SSH password (key preferred) |
| `ssh_port` | `22` | SSH port |

The SSH connection uses paramiko with:

- Lazy connection (connects on first command)
- Persistent connection (single TCP session for all commands)
- SFTP for file upload/download
- Automatic retry with exponential backoff (3 retries)

### WinRM

| Field | Default | Description |
|-------|---------|-------------|
| `connection_type` | `ssh` | Set to `winrm` for Windows |
| `winrm_user` | `Administrator` | WinRM username |
| `winrm_password` | `""` | WinRM password |
| `winrm_ssl` | `false` | Use HTTPS (port 5986) |
| `winrm_port` | auto | 5985 (HTTP) or 5986 (HTTPS) |

### Timeout Fields

| Field | Default | Description |
|-------|---------|-------------|
| `startup_timeout` | `300` | Max seconds to wait for VPS to become "active" in provider API |
| `boot_timeout` | `180` | Max seconds to wait for SSH/WinRM port to be reachable |
| `login_timeout` | `300` | Max seconds to wait for successful authentication (real SSH/WinRM login) |

The login timeout is separate from boot timeout because a VPS may have the SSH port open but not yet accept logins (e.g. cloud-init still configuring users/keys).

## Credential Redaction

Cloud credentials (SSH passwords, WinRM passwords, API tokens) are automatically registered with the log redaction filter. They will never appear in plaintext in console output or debug logs, even with `OFX_DEBUG=1`.

Redacted values appear as `***` in all log output.

## Opsec Mode

When `opsec_mode: true`, commands are not passed directly to the shell. Instead:

**Linux (SSH):**
```
1. Write command to /tmp/.{random_hex}
2. chmod +x the temp file
3. Execute the temp file
4. Delete the temp file
```

**Windows (WinRM):**
```
1. Write command to C:\Windows\Temp\{random}.bat
2. Execute the batch file
3. Delete the batch file
```

This prevents the actual command content from being visible in `ps aux`, `top`, or process monitoring tools.
