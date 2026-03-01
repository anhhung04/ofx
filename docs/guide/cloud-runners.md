# Cloud Runners

OFX can run jobs on cloud VPS instances — automatically provisioning, executing, and destroying them.

## Overview

Cloud runners extend OFX workflows to execute on remote infrastructure:

- **DigitalOcean** — Spin up Droplets via the API
- **AWS EC2** — Launch instances on EC2
- **Static** — Use pre-existing VPS without lifecycle management

Jobs with a `cloud` configuration are automatically routed to the `CloudJobRunner`, which handles:

1. **Provisioning** — Create the VPS (or connect to existing)
2. **Connectivity** — Wait for SSH/WinRM to be ready
3. **Execution** — Run each step remotely via SSH or WinRM
4. **Cleanup** — Download outputs and destroy the VPS

## Quick Start

### 1. Install cloud dependencies

```bash
# DigitalOcean
pip install ofx[digitalocean]

# AWS EC2
pip install ofx[aws]

# Both
pip install ofx[cloud]
```

### 2. Set up a cloud profile

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
      - run: nmap -sV 10.0.0.0/24 -oA /tmp/ofx-*/output/scan
```

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
| `ssh_password` | string | `""` | SSH password (uses `sshpass`) |
| `ssh_port` | int | `22` | SSH port |
| `connection_type` | string | `"ssh"` | Connection type (`ssh` or `winrm`) |
| `winrm_user` | string | `"Administrator"` | WinRM username |
| `winrm_password` | string | `""` | WinRM password |
| `winrm_ssl` | bool | `false` | Use HTTPS for WinRM |
| `winrm_port` | int | auto | WinRM port (auto: 5985/5986) |
| `opsec_mode` | bool | `false` | Execute via temp files (avoids ps visibility) |
| `log_commands` | bool | `false` | Log all commands locally |
| `auto_destroy` | bool | `true` | Destroy instance after job completes |
| `startup_timeout` | int | `300` | Max seconds to wait for instance boot |
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

## Fleet Mode (Distributed Execution)

Run jobs across multiple VPS simultaneously — like [Axiom](https://github.com/pry0cc/axiom):

```yaml
jobs:
  distributed-scan:
    cloud: do-small
    strategy:
      fleet:
        count: 5                    # Number of VPS instances
        input: targets.txt          # Input to distribute
        distribution: chunk         # Split method
      max_parallel: 5
    steps:
      - run: |
          nmap -iL {{ matrix.fleet_input_file }} \
               -oA /tmp/ofx-*/output/scan-{{ matrix.fleet_index }}
```

### Fleet configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `count` | int | required | Number of fleet instances |
| `input` | string | `""` | Input data or file to distribute |
| `distribution` | string | `"chunk"` | Split method |
| `expand_cidrs` | bool | `true` | Expand CIDRs to individual IPs |
| `min_prefix` | int | `24` | Minimum CIDR prefix for subnet mode |
| `exclude` | list | `[]` | IPs/CIDRs to exclude |

### Distribution methods

| Method | Description |
|--------|-------------|
| `chunk` | Even sequential chunks (default) |
| `round-robin` | Round-robin distribution |
| `subnet` | Groups by /24 subnet, assigns to least-full bucket |
| `line` | One line per instance |

### Input formats

The fleet input parser supports:

- **Single IP**: `192.168.1.1`
- **CIDR**: `10.0.0.0/24`
- **IP range**: `10.0.0.1-10.0.0.50`
- **Short range**: `10.0.0.1-50`
- **Hostname**: `server1.example.com`
- **Comma-separated**: `10.0.0.1,10.0.0.2,host.com`
- **File**: Path to a file with one target per line
- **Mixed**: Combine any of the above

### Fleet template variables

Each fleet instance gets context variables:

| Variable | Description |
|----------|-------------|
| `{{ matrix.fleet_index }}` | Instance index (0-based) |
| `{{ matrix.fleet_total }}` | Total number of instances |
| `{{ matrix.fleet_input_file }}` | Path to this instance's input chunk |
| `{{ matrix.fleet_target_count }}` | Number of targets in this chunk |

### Static fleet

Use pre-existing hosts without provisioning:

```yaml
jobs:
  multi-host:
    cloud:
      provider: static
      hosts:
        - host: 10.0.0.1
          ssh_user: root
        - host: 10.0.0.2
          ssh_user: root
        - host: 10.0.0.3
          ssh_user: operator
    strategy:
      fleet:
        count: 3
        input: targets.txt
        distribution: round-robin
    steps:
      - run: masscan -iL {{ matrix.fleet_input_file }} -p 1-65535 --rate 10000
```

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

### Fleet management

```bash
# Create a fleet of 5 instances
ofx cloud fleet create 5 --profile do-small --prefix scan-fleet

# Destroy fleet instances by prefix
ofx cloud fleet destroy --prefix scan-fleet --provider digitalocean
```

## Authentication

### DigitalOcean

Set the `DIGITALOCEAN_TOKEN` environment variable:

```bash
export DIGITALOCEAN_TOKEN="dop_v1_..."
ofx flow run my-cloud-workflow
```

Or pass via profile extras in `~/.ofx/cloud.yml`:

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

## Example Workflows

### Distributed subdomain enumeration

```yaml
name: distributed-recon
jobs:
  enum:
    cloud:
      profile: do-small
    strategy:
      fleet:
        count: 3
        input: domains.txt
        distribution: round-robin
    steps:
      - run: |
          apt-get update && apt-get install -y subfinder httpx-toolkit
      - run: |
          while read domain; do
            subfinder -d "$domain" -silent >> subs.txt
          done < {{ matrix.fleet_input_file }}
          httpx -l subs.txt -o live-{{ matrix.fleet_index }}.txt
```

### Cloud + local hybrid

```yaml
name: hybrid-workflow
jobs:
  scan:
    cloud: do-small
    steps:
      - run: nmap -sV -p- target.com -oA /tmp/ofx-*/output/nmap

  analyze:
    needs: [scan]
    steps:
      - run: |
          # Runs locally, uses output from cloud scan
          cat output/scan/nmap.gnmap | grep open
```
