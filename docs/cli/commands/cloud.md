# Cloud Commands

> Manage cloud providers, profiles, instances, images, and fleet operations.

---

## Usage

```bash
ofx cloud <subcommand> [options]
```

---

## Overview

The `cloud` command group provides full lifecycle management for cloud VPS resources used by OFX workflows. It supports three providers:

| Provider | Description |
|----------|-------------|
| **static** | Wraps pre-existing hosts (no provisioning/teardown) |
| **digitalocean** | DigitalOcean Droplets via the `pydo` SDK |
| **aws** | AWS EC2 instances via `boto3` |

Cloud profiles are stored in `~/.ofx/cloud.yml` and can be referenced by name in workflows or session commands.

---

## Top-Level Commands

### test

Test connectivity to a remote host via SSH or WinRM.

```bash
ofx cloud test <host> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--port` | `-p` | Port to test (default: `22`) |
| `--connection` | `-c` | Connection type: `ssh` or `winrm` (default: `ssh`) |
| `--timeout` | `-t` | Timeout in seconds (default: `30`) |

```bash
# Test SSH connectivity
ofx cloud test 10.0.0.5

# Test WinRM on a custom port
ofx cloud test 10.0.0.10 --connection winrm --port 5986 --timeout 60
```

---

### providers

List all registered cloud providers.

```bash
ofx cloud providers
```

---

## Profile Management

Profiles store reusable cloud configurations (provider, region, size, image, SSH settings).

```bash
ofx cloud profile <subcommand>
```

### profile list

List all configured cloud profiles.

```bash
ofx cloud profile list
```

### profile add

Add or update a cloud profile.

```bash
ofx cloud profile add <name> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--provider` | `-p` | Cloud provider (`digitalocean`, `aws`, `static`) |
| `--region` | `-r` | Region/datacenter |
| `--size` | `-s` | Instance size/type |
| `--image` | `-i` | OS image |
| `--ssh-user` | | SSH username |
| `--ssh-key` | | SSH key path |
| `--ssh-password` | | SSH password |
| `--connection` | | Connection type: `ssh` or `winrm` |
| `--auto-destroy/--no-auto-destroy` | | Auto-destroy after completion (default: on) |
| `--default` | | Set as default profile |

### profile remove

Remove a cloud profile.

```bash
ofx cloud profile remove <name>
```

### profile default

Set the default cloud profile.

```bash
ofx cloud profile default <name>
```

### profile show

Show details of a cloud profile. If no name is given, shows the default profile.

```bash
ofx cloud profile show [name]
```

### Profile Examples

```bash
# Add a DigitalOcean profile
ofx cloud profile add do-nyc \
  --provider digitalocean \
  --region nyc3 \
  --size s-2vcpu-4gb \
  --image ubuntu-22-04-x64 \
  --ssh-user root \
  --ssh-key ~/.ssh/id_ed25519 \
  --default

# Add an AWS profile
ofx cloud profile add aws-east \
  --provider aws \
  --region us-east-1 \
  --size t3.medium \
  --image ami-0abcdef1234567890

# Add a static host profile
ofx cloud profile add lab-box \
  --provider static \
  --ssh-user admin \
  --ssh-key ~/.ssh/lab_key

# View default profile config
ofx cloud profile show
```

---

## Instance Management

Manage individual cloud instances (create, list, destroy).

```bash
ofx cloud instance <subcommand>
```

### instance list

List cloud instances for a provider or profile.

```bash
ofx cloud instance list [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--provider` | `-p` | Cloud provider |
| `--profile` | | Use a cloud profile |

### instance create

Create a cloud instance manually.

```bash
ofx cloud instance create [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--profile` | | Use a cloud profile |
| `--provider` | `-p` | Cloud provider |
| `--name` | `-n` | Instance name (default: `ofx-manual`) |
| `--region` | `-r` | Region |
| `--size` | `-s` | Instance size |
| `--image` | `-i` | OS image |
| `--wait/--no-wait` | | Wait until the instance is ready (default: on) |

### instance destroy

Destroy a cloud instance.

```bash
ofx cloud instance destroy <instance_id> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--provider` | `-p` | Cloud provider |
| `--profile` | | Use a cloud profile |
| `--force` | `-f` | Skip confirmation prompt |

### Instance Examples

```bash
# List instances using a profile
ofx cloud instance list --profile do-nyc

# Create a temporary instance
ofx cloud instance create --profile do-nyc --name recon-box

# Destroy when done
ofx cloud instance destroy abc123 --profile do-nyc --force
```

---

## Image / Snapshot Management

Manage cloud snapshots and images.

```bash
ofx cloud image <subcommand>
```

### image list

List available snapshots for a provider.

```bash
ofx cloud image list [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--provider` | `-p` | Cloud provider |
| `--profile` | | Use a cloud profile |

### image create

Create a snapshot from a running instance.

```bash
ofx cloud image create <instance_id> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--name` | `-n` | Snapshot name (default: `ofx-snapshot-<id>`) |
| `--provider` | `-p` | Cloud provider |
| `--profile` | | Use a cloud profile |

### image delete

Delete a snapshot.

```bash
ofx cloud image delete <snapshot_id> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--provider` | `-p` | Cloud provider |
| `--profile` | | Use a cloud profile |
| `--force` | `-f` | Skip confirmation prompt |

### Image Examples

```bash
# Snapshot a configured instance for reuse
ofx cloud image create abc123 --name "recon-toolbox-v2" --profile do-nyc

# List snapshots
ofx cloud image list --profile do-nyc

# Delete old snapshot
ofx cloud image delete snap-xyz --profile do-nyc --force
```

---

## Fleet Management

Create and manage fleets of cloud instances for distributed workflow execution.

```bash
ofx cloud fleet <subcommand>
```

### fleet create

Create a fleet of cloud instances.

```bash
ofx cloud fleet create <count> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--profile` | | Cloud profile to use |
| `--provider` | `-p` | Cloud provider |
| `--prefix` | | Instance name prefix (default: `ofx-fleet`) |
| `--region` | `-r` | Region |
| `--size` | `-s` | Instance size |
| `--image` | `-i` | OS image |

### fleet run

Submit a workflow across multiple fleet instances with target distribution.

Each instance receives a chunk of the targets. The chunk file path is passed to the workflow as an input variable.

```bash
ofx cloud fleet run <workflow> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--targets` | `-t` | Targets: file path, CIDR, or comma-separated IPs |
| `--count` | `-n` | Number of fleet instances (auto-calculated from targets if `0`) |
| `--profile` | | Cloud profile (required) |
| `--distribution` | `-d` | Distribution mode: `chunk`, `round-robin`, `subnet`, `line` (default: `chunk`) |
| `--job` | `-j` | Job ID to run |
| `--name` | | Fleet run name |
| `--input` | `-i` | Input key=value pairs (repeatable) |
| `--target-var` | | Input variable name for the chunk file (default: `targets_file`) |

#### Distribution Modes

| Mode | Description |
|------|-------------|
| `chunk` | Splits targets into N equal chunks |
| `round-robin` | Distributes targets one-by-one across instances |
| `subnet` | Groups targets by subnet |
| `line` | Splits input file by line count |

### fleet status

Show status of all sessions in a fleet group.

```bash
ofx cloud fleet status <fleet_group_id> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--refresh` | `-r` | Probe running sessions for latest status |

### fleet results

Fetch and aggregate results from all sessions in a fleet group.

```bash
ofx cloud fleet results <fleet_group_id> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Output directory for aggregated results |
| `--passphrase` | `-p` | Encrypt results with passphrase |
| `--skip-running` | | Skip sessions still running (fetch completed only) |

### fleet cancel

Cancel all running sessions in a fleet group.

```bash
ofx cloud fleet cancel <fleet_group_id> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--force` | `-f` | Skip confirmation prompt |

### fleet destroy

Destroy fleet instances by tag or name prefix.

```bash
ofx cloud fleet destroy [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--tag` | | Destroy instances with this tag |
| `--prefix` | | Instance name prefix to match (default: `ofx-fleet`) |
| `--provider` | `-p` | Cloud provider |
| `--profile` | | Cloud profile |
| `--force` | `-f` | Skip confirmation prompt |

### Fleet Examples

```bash
# Distribute a scan across 5 instances
ofx cloud fleet run scan.yml \
  --targets targets.txt \
  --count 5 \
  --profile do-nyc \
  --distribution chunk

# Scan a /24 with round-robin distribution
ofx cloud fleet run scan.yml \
  --targets 10.0.0.0/24 \
  --count 10 \
  --profile do-nyc \
  --distribution round-robin

# Check fleet progress
ofx cloud fleet status a1b2c3d4 --refresh

# Fetch all results
ofx cloud fleet results a1b2c3d4 --output ./fleet-results

# Clean up
ofx cloud fleet cancel a1b2c3d4 --force
ofx cloud fleet destroy --profile do-nyc --force
```

---

!!! tip "Cloud Tips"
    - Use `ofx cloud test` to verify connectivity before running cloud workflows
    - Set a default profile with `ofx cloud profile default <name>` so you don't have to pass `--profile` every time
    - Snapshots let you pre-install tools and skip setup time on subsequent runs
    - Fleet results are automatically routed to the project's `evidence/sessions/` directory when a project is active

---

## See Also

- [**Session Commands**](session.md) — Detached session management
- [**Cloud Runners Guide**](../../guide/cloud-runners.md) — Using cloud in workflows
- [**Cloud Configuration**](../../guide/cloud/configuration.md) — Profile and provider setup
- [**Fleet Guide**](../../guide/cloud/fleet.md) — Fleet distribution deep dive
