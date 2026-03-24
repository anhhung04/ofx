# Session Commands

> Manage detached workflow sessions — fire-and-forget execution with lifecycle tracking, encryption, and result retrieval.

---

## Usage

```bash
ofx session <subcommand> [options]
```

---

## Key Concepts

### Local vs Cloud Sessions

Sessions run workflows in the background as **detached processes** — either on the local machine or on a provisioned cloud VPS.

| Target | How it works |
|--------|-------------|
| **Local** (`--local`) | Runs as a background subprocess on the current host |
| **Cloud** (`--cloud <profile>`) | Provisions a VPS via the named cloud profile, uploads the workflow, executes remotely |

### Session Lifecycle

Sessions transition through these states:

```
provisioning → uploading → running → completed → fetched → encrypted → destroyed
                                   ↘ failed
                                   ↘ canceled
```

### At-Rest Encryption

Session results can be encrypted at fetch time with a passphrase (Fernet-based). Cloud sessions also benefit from automatic AES-256-CBC at-rest encryption on the remote host — the encryption key is shredded after use.

---

## Subcommands

### submit

Submit a workflow as a detached session.

```bash
ofx session submit <workflow> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--job` | `-j` | Job ID to run (default: full workflow) |
| `--local` | `-l` | Run as local background process |
| `--cloud` | `-c` | Cloud profile to use |
| `--name` | `-n` | Session name/tag |
| `--input` | `-i` | Input key=value pairs (repeatable) |

!!! note
    You cannot combine `--local` and `--cloud` — pick one execution target.

---

### list

List all sessions with optional filters.

```bash
ofx session list [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--status` | `-s` | Filter by status (e.g. `running`, `completed`, `failed`) |
| `--target` | `-t` | Filter by target: `local` or `cloud` |
| `--project` | | Filter by project name |

---

### status

Check the status of a session. Probes the PID if the session is still running.

```bash
ofx session status <session_id>
```

---

### logs

View session output log (tail last N lines).

```bash
ofx session logs <session_id> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--tail` | `-n` | Number of lines to show (default: `50`) |

---

### fetch

Fetch results from a completed session. Optionally encrypt with a passphrase.

```bash
ofx session fetch <session_id> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--passphrase` | `-p` | Encrypt results with this passphrase |
| `--output` | `-o` | Output directory for results |

---

### decrypt

Decrypt previously encrypted session results.

```bash
ofx session decrypt <session_id> --passphrase <pw> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--passphrase` | `-p` | Decryption passphrase (prompted if not given) |
| `--output` | `-o` | Output directory |

---

### cancel

Cancel a running session (kills the process).

```bash
ofx session cancel <session_id>
```

---

### destroy

Destroy a session. For cloud sessions, tears down the VPS. For local sessions, cleans up the workspace.

```bash
ofx session destroy <session_id> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--force` | `-f` | Force destroy even if the session is still running |

---

### clean

Remove old session data from disk. Shows a confirmation prompt before deleting.

```bash
ofx session clean [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--older-than` | | Age threshold (e.g. `7d`, `24h`, `30m`, `3600s`) |
| `--status` | `-s` | Comma-separated statuses to clean (default: `completed,fetched,encrypted,destroyed,canceled`) |
| `--yes` | `-y` | Skip confirmation prompt |

---

### guard

Non-interactive auto-cleanup for unattended environments (cron, CI).

```bash
ofx session guard [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--older-than` | | Age threshold (default: `7d`) |
| `--status` | `-s` | Comma-separated statuses to clean (default: `completed,fetched,encrypted,destroyed,canceled,failed`) |

---

### bundle

Create a tar.gz artifacts bundle for a session containing metadata and results.

```bash
ofx session bundle <session_id> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Output tar.gz file path |

---

## Examples

### Submit a Local Session

```bash
ofx session submit recon.yml --local --input target=10.0.0.0/24
```

### Submit to Cloud

```bash
ofx session submit scan.yml --cloud do-nyc --name nightly-scan --input target=example.com
```

### Check Status and Fetch Results

```bash
# Check status
ofx session status abc123

# View live output
ofx session logs abc123 --tail 100

# Fetch results with encryption
ofx session fetch abc123 --passphrase "s3cret" --output ./results
```

### Decrypt Results Later

```bash
ofx session decrypt abc123 --passphrase "s3cret" --output ./decrypted
```

### Cleanup Old Sessions

```bash
# Interactive cleanup of sessions older than 7 days
ofx session clean --older-than 7d

# Non-interactive guard (e.g. in cron)
ofx session guard --older-than 3d
```

### Bundle Artifacts

```bash
ofx session bundle abc123 --output ./evidence/session-abc123.tar.gz
```

---

!!! tip "Session Lifecycle Tips"
    - Use `ofx session list --status running` to monitor active sessions
    - Cloud sessions auto-destroy the VPS after completion by default
    - The `guard` command is ideal for cron jobs: `0 3 * * * ofx session guard --older-than 7d`
    - Use `--name` when submitting to make sessions easier to identify in `list` output

---

## See Also

- [**Cloud Commands**](cloud.md) — Cloud profile and instance management
- [**Detached Sessions Guide**](../../guide/cloud-sessions.md) — In-depth session concepts
- [**Run Command**](run.md) — Interactive workflow execution
