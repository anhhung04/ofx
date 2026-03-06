# Cloud Runners

> [!INFO]
> OFX can run jobs on cloud VPS instances—provision, execute, and destroy automatically.

---

## Overview

Cloud runners extend OFX workflows to execute on remote infrastructure:

| Provider         | Description                                 |
|------------------|---------------------------------------------|
| **DigitalOcean** | Spin up Droplets via API                    |
| **AWS EC2**      | Launch EC2 instances                        |
| **Static**       | Use pre-existing VPS (no lifecycle)         |

Jobs with a `cloud` configuration are routed to the `CloudJobRunner`:

1. **Provisioning** — Create or connect to VPS
2. **Connectivity** — Wait for SSH/WinRM
3. **Execution** — Run steps remotely
4. **Cleanup** — Download outputs & destroy VPS

---

## Quick Start

### 1. Install Cloud Dependencies

```bash
# DigitalOcean
pip install ofx[digitalocean]
# AWS EC2
pip install ofx[aws]
# Both
pip install ofx[cloud]
```

> [!TIP]
> See [src/ofx/cloud/providers/](../../src/ofx/cloud/providers/) for provider code.

---

### 2. Set Up a Cloud Profile

```bash
ofx cloud profile add do-small \
  --provider digitalocean \
  --region nyc1 \
  --size s-1vcpu-1gb \
  --image ubuntu-24-04-x64 \
  --ssh-user root \
  --ssh-key ~/.ssh/id_rsa \
  --default
```

### 3. Use in a workflow

```yaml
name: cloud-scan
jobs:
  scan:
    cloud: do-small          # Reference profile by name
    steps:
      - run: apt-get update && apt-get install -y nmap
      - run: nmap -sV 10.0.0.0/24 -oA output/scan
```

## In-Depth Topics

| Topic | Description |
|-------|-------------|
| [Cloud Configuration](cloud/configuration.md) | Profiles, providers, inline config, authentication |
| [Variables & Environment](cloud/variables.md) | Template variables, env passing, secrets on VPS |
| [Fleet Mode](cloud/fleet.md) | Distributed execution across multiple VPS instances |
| [Lifecycle & Cleanup](cloud/lifecycle.md) | Provisioning, output collection, failure handling, cleanup |
| [Sessions](cloud-sessions.md) | Detached fire-and-forget execution with result retrieval |

## Workflow Configuration

### Inline cloud config

```yaml
jobs:
  recon:
    cloud:
      provider: digitalocean
      region: nyc1
      size: s-2vcpu-4gb
      image: ubuntu-24-04-x64
      ssh_user: root
      ssh_key: ~/.ssh/id_rsa
      auto_destroy: true
      opsec_mode: true
    steps:
      - run: |
          subfinder -d example.com -o subs.txt
          httpx -l subs.txt -o live.txt
```

### Profile reference with overrides

```yaml
jobs:
  heavy:
    cloud:
      profile: do-small      # Base from profile
      size: s-4vcpu-8gb      # Override size
    steps:
      - run: nuclei -l targets.txt
```

### Cloud config fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `profile` | string | `""` | Named profile from `~/.ofx/cloud.yml` |
| `provider` | string | `""` | Cloud provider (`digitalocean`, `aws`, `static`) |
| `region` | string | `""` | Region/datacenter |
| `size` | string | `""` | Instance size/type |
| `image` | string | `""` | OS image ID or slug |
| `ssh_user` | string | `"root"` | SSH username |
| `ssh_key` | string | `""` | Path to SSH private key |
| `ssh_password` | string | `""` | SSH password |
| `ssh_port` | int | `22` | SSH port |
| `connection_type` | string | `"ssh"` | Connection type (`ssh` or `winrm`) |
| `winrm_user` | string | `"Administrator"` | WinRM username |
| `winrm_password` | string | `""` | WinRM password |
| `winrm_ssl` | bool | `false` | Use HTTPS for WinRM |
| `winrm_port` | int | auto | WinRM port (auto: 5985/5986) |
| `host` | string | `""` | Hostname/IP for static provider |
| `opsec_mode` | bool | `false` | Execute via temp files (avoids ps visibility) |
| `log_commands` | bool | `false` | Log all commands locally |
| `auto_destroy` | bool | `true` | Destroy instance after job completes |
| `startup_timeout` | int | `300` | Max seconds to wait for instance boot |
| `boot_timeout` | int | `180` | Max seconds to wait for SSH/WinRM port |
| `login_timeout` | int | `300` | Max seconds to wait for successful SSH/WinRM login |
| `tags` | list | `[]` | Instance tags |

### Provider-specific fields

**DigitalOcean:**

| Field | Description |
|-------|-------------|
| `vpc_uuid` | DigitalOcean VPC UUID |
| `project_id` | DigitalOcean project ID |

**AWS EC2:**

| Field | Description |
|-------|-------------|
| `key_pair_name` | AWS key pair name |
| `security_group` | Security group ID |
| `subnet_id` | Subnet ID |
| `iam_instance_profile` | IAM instance profile |

## Cloud Profiles

Profiles store reusable cloud configurations in `~/.ofx/cloud.yml`:

```yaml
default: do-small
profiles:
  do-small:
    provider: digitalocean
    region: nyc1
    size: s-1vcpu-1gb
    image: ubuntu-24-04-x64
    ssh_user: root
    ssh_key: ~/.ssh/id_rsa

  aws-medium:
    provider: aws
    region: us-east-1
    size: t3.medium
    image: ami-0c55b159cbfafe1f0
    ssh_user: ubuntu
    ssh_key: ~/.ssh/aws-key.pem
    key_pair_name: my-key
    security_group: sg-12345678

  lab-box:
    provider: static
    host: 192.168.1.100
    ssh_user: root
    ssh_key: ~/.ssh/lab_key
```

### CLI profile management

```bash
# List profiles
ofx cloud profile list

# Add a profile
ofx cloud profile add my-do \
  --provider digitalocean \
  --region lon1 \
  --size s-2vcpu-2gb \
  --image ubuntu-24-04-x64

# Show profile details
ofx cloud profile show my-do

# Set default
ofx cloud profile default my-do

# Remove
ofx cloud profile remove old-profile
```

## Static Provider

For pre-existing VPS that don't need lifecycle management:

```yaml
jobs:
  pentest:
    cloud:
      provider: static
      host: 10.0.0.50
      ssh_user: operator
      ssh_key: ~/.ssh/range_key
    steps:
      - run: ./run-exploit.sh
```

The static provider:

- Never creates or destroys instances
- Verifies SSH/WinRM connectivity before execution
- Supports single host or fleet of hosts
- Passes through all SSH/WinRM configuration

## Windows VPS (WinRM)

Cloud jobs support Windows instances via WinRM:

```yaml
jobs:
  windows-task:
    cloud:
      provider: aws
      region: us-east-1
      size: t3.medium
      image: ami-0abcd1234windows
      connection_type: winrm
      winrm_user: Administrator
      winrm_password: "{{ secrets.WIN_PASSWORD }}"
      winrm_ssl: true
    steps:
      - run: whoami
      - run: Get-Process | Sort-Object CPU -Descending | Select-Object -First 10
```

## Opsec Mode

When `opsec_mode: true`:

**SSH (Linux):**
- Commands are written to a random temp file (`/tmp/.{random}`)
- The file is made executable and run
- Only the temp file path appears in process listings
- Temp files are cleaned up after execution

**WinRM (Windows):**
- Commands are written to a `.bat` file in `C:\Windows\Temp`
- Executed via the batch file
- Deleted after execution

This hides the actual command content from `ps`, `top`, and similar enumeration.

## Authentication

### DigitalOcean

Tokens are resolved in this order:

1. `token` field in profile `extra:` config
2. `DIGITALOCEAN_TOKEN` environment variable
3. OFX secret named `digitalocean_token` (from `ofx secret set digitalocean_token=dop_v1_...`)

```bash
# Option 1: Environment variable
export DIGITALOCEAN_TOKEN="dop_v1_..."

# Option 2: OFX secret store (encrypted, persisted)
ofx secret set digitalocean_token=dop_v1_...

# Option 3: Profile extras in ~/.ofx/cloud.yml
```

```yaml
profiles:
  do-prod:
    provider: digitalocean
    extra:
      token: dop_v1_...
```

### AWS EC2

Uses the standard AWS credential chain:

```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="us-east-1"
```

Or configure via `~/.aws/credentials`.

## CLI Instance Management

```bash
# List available providers
ofx cloud providers

# Create an instance manually
ofx cloud instance create --profile do-small --name test-box

# List instances
ofx cloud instance list --provider digitalocean

# Destroy an instance
ofx cloud instance destroy <instance-id> --provider digitalocean

# Test connectivity
ofx cloud test 192.168.1.100 --port 22 --connection ssh
```

### Snapshot/Image management

```bash
# Create snapshot from running instance
ofx cloud image create <instance-id> --name my-snapshot --provider digitalocean

# List snapshots
ofx cloud image list --provider digitalocean

# Delete snapshot
ofx cloud image delete <snapshot-id> --provider digitalocean
```

## Example Workflows

### Cloud + local hybrid

```yaml
name: hybrid-workflow
jobs:
  scan:
    cloud: do-small
    steps:
      - run: nmap -sV -p- target.com -oA output/nmap

  analyze:
    needs: [scan]
    steps:
      - run: |
          # Runs locally, uses output from cloud scan
          cat output/scan/nmap.gnmap | grep open
```

### Multi-cloud

Different jobs can use different providers:

```yaml
name: multi-cloud
jobs:
  recon:
    cloud: do-nyc
    steps:
      - run: subfinder -d target.com -o output/subs.txt

  exploit:
    cloud:
      provider: aws
      region: us-east-1
      size: t3.medium
    needs: [recon]
    steps:
      - run: nuclei -l targets.txt

  report:
    needs: [exploit]
    steps:
      - run: echo "All done"   # Runs locally
```
