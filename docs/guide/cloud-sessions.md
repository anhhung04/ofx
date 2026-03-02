# Detached Sessions

Detached sessions let you fire off a workflow job, disconnect, and come back later to check status, retrieve results, or encrypt the output.

Sessions work in two modes:

- **Local** — runs as a background process on your machine
- **Cloud** — provisions a VPS, runs on it, then destroys it when done

## Quick Start

### Submit a local session

```bash
ofx session submit scan.yml --local --name nmap-run
```

### Submit a cloud session

```bash
ofx session submit scan.yml --cloud do-small --name cloud-scan
```

### Check status and fetch results

```bash
ofx session status abc12345
ofx session logs abc12345 --tail 100
ofx session fetch abc12345 --passphrase s3cret
```

## Session Lifecycle

Sessions move through these states:

```
provisioning → uploading → running → completed → fetched → encrypted → destroyed
                                   ↘ failed
                          canceled ←
```

| State | Description |
|-------|-------------|
| `provisioning` | Cloud VPS being created (skipped for local) |
| `uploading` | Script uploaded to remote host (skipped for local) |
| `running` | Job is executing |
| `completed` | Job finished successfully |
| `failed` | Job exited with errors |
| `canceled` | Manually canceled via `session cancel` |
| `fetched` | Results downloaded locally |
| `encrypted` | Results encrypted with a passphrase |
| `destroyed` | VPS destroyed / workspace cleaned up |

## CLI Commands

### `session submit`

Submit a workflow job as a detached session.

```bash
ofx session submit <workflow> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--local` | `-l` | Run as a local background process (default) |
| `--cloud <profile>` | `-c` | Run on a cloud VPS using the named profile |
| `--job <id>` | `-j` | Job ID to run (default: first job in workflow) |
| `--name <tag>` | `-n` | Human-readable session name |
| `--input KEY=VAL` | `-i` | Pass inputs (repeatable) |
| `--env KEY=VAL` | `-e` | Set environment variables (repeatable) |

You cannot use `--local` and `--cloud` together.

**Examples:**

```bash
# Local session with inputs
ofx session submit recon.yml --local -n recon-run -i target=10.0.0.0/24 -i threads=50

# Cloud session on a DigitalOcean profile
ofx session submit scan.yml --cloud do-small --name cloud-scan -i target=192.168.1.0/24
```

### `session list`

List all sessions, optionally filtered.

```bash
ofx session list [--status running] [--target local|cloud]
```

### `session status`

Probe a session's current state. For running sessions, this checks whether the process is still alive and parses log markers to detect completion.

```bash
ofx session status <session-id>
```

### `session logs`

View the output log (last N lines).

```bash
ofx session logs <session-id> [--tail 100]
```

### `session fetch`

Download results from a completed session. Optionally encrypt them in one step.

```bash
# Fetch results (unencrypted)
ofx session fetch <session-id>

# Fetch and encrypt with passphrase
ofx session fetch <session-id> --passphrase s3cret

# Fetch to a specific directory
ofx session fetch <session-id> --output /tmp/results
```

### `session decrypt`

Decrypt previously encrypted results. The passphrase is prompted interactively if not provided.

```bash
ofx session decrypt <session-id> --passphrase s3cret [--output ./decrypted]
```

### `session cancel`

Kill a running session's process (sends SIGTERM locally, kills via SSH for cloud).

```bash
ofx session cancel <session-id>
```

### `session destroy`

Destroy a cloud VPS or clean up a local session workspace. Use `--force` to destroy even if the session is still running.

```bash
ofx session destroy <session-id>
ofx session destroy <session-id> --force
```

### `session clean`

Bulk-remove old session data from disk.

```bash
# Remove sessions older than 7 days
ofx session clean --older-than 7d

# Remove only completed sessions older than 24 hours
ofx session clean --older-than 24h --status completed

# Skip confirmation
ofx session clean --older-than 7d --yes
```

Duration formats: `7d` (days), `24h` (hours), `30m` (minutes), `3600s` (seconds).

Default statuses cleaned: `completed`, `fetched`, `encrypted`, `destroyed`, `canceled`.

## Encryption

Session results can be encrypted at fetch time or separately afterward.

### How it works

1. The results directory is archived into a `.tar.gz`
2. A random 16-byte salt is generated
3. The passphrase is derived into a Fernet key using PBKDF2-HMAC-SHA256 (480,000 iterations)
4. The archive is encrypted with Fernet (AES-128-CBC + HMAC)
5. The output file is `results.enc` = `[16-byte salt][encrypted data]`

### Encrypt at fetch time

```bash
ofx session fetch abc12345 --passphrase s3cret
```

### Decrypt later

```bash
ofx session decrypt abc12345 --passphrase s3cret
```

!!! warning "Passphrase recovery"
    There is no way to recover encrypted results without the passphrase. Store it securely.

## Local Sessions

Local sessions run as detached background processes (`start_new_session=True`). The generated script:

- Logs all output to `~/.ofx/sessions/<id>/session.log`
- Creates a `work/` directory for step execution
- Writes `__OFX_DONE__` or `__OFX_FAIL__` markers to the log on completion
- Runs independently of the submitting terminal

### How status detection works

1. Check if the PID is still alive (`os.kill(pid, 0)`)
2. Parse the log file for `__OFX_DONE__` / `__OFX_FAIL__` markers
3. Update the session status accordingly

## Cloud Sessions

Cloud sessions provision a VPS, upload the script, execute it via SSH with `nohup`, and track the remote PID.

### Requirements

- A configured cloud profile (`ofx cloud profile add`)
- SSH key access to the provisioned VPS

### Workflow

1. **Provision** — Create VPS using the cloud profile
2. **Wait** — Poll until SSH is ready
3. **Upload** — SCP the generated script to the VPS
4. **Execute** — `nohup bash /tmp/ofx_session.sh > output.log 2>&1 & echo $!`
5. **Disconnect** — Return session ID to user
6. **Status check** — SSH back in, check PID, tail log for markers
7. **Fetch** — SCP results directory back to local machine
8. **Destroy** — Terminate the VPS

### Example end-to-end

```bash
# 1. Submit
ofx session submit masscan.yml --cloud do-small -n mass-scan -i targets=targets.txt

# 2. Check later
ofx session status a1b2c3d4
ofx session logs a1b2c3d4

# 3. Fetch and encrypt
ofx session fetch a1b2c3d4 --passphrase hunter2

# 4. Destroy VPS
ofx session destroy a1b2c3d4

# 5. Decrypt when needed
ofx session decrypt a1b2c3d4 --passphrase hunter2 --output ./results
```

## Session Storage

Sessions are persisted as JSON files under `~/.ofx/sessions/<id>/session.json`. Each session directory may also contain:

- `session.log` — stdout/stderr from the job
- `session_script.sh` — the generated bash script
- `work/` — working directory for step execution (local)
- `results/` — fetched results
- `results.enc` — encrypted results archive

File locking (`fcntl.flock`) ensures safe concurrent access.

## Workflow YAML for Sessions

Sessions run a single job from a workflow. The workflow format is unchanged:

```yaml
name: network-scan
jobs:
  scan:
    steps:
      - name: run-nmap
        run: nmap -sV -oA output/scan {{ inputs.target }}
      - name: parse-results
        run: |
          mkdir -p output
          grep "open" output/scan.nmap > output/open-ports.txt
```

Submit with:

```bash
ofx session submit network-scan.yml --local -i target=10.0.0.0/24
```

The session extracts the specified job (or first job), generates a self-contained script from its steps, and runs it detached.
