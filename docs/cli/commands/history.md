# Run History

Track and review past workflow executions.

## Usage

```bash
# Show last 20 runs
ofx flow history

# Show last 50 runs with details
ofx flow history -n 50 -v

# Filter by workflow name
ofx flow history -w subdomain-recon

# Filter by status
ofx flow history -s failed

# Combine filters
ofx flow history -w recon -s completed -n 10

# Clear all history
ofx flow history --clear

# Prune to keep only last 100 entries
ofx flow history --prune 100
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--limit` | `-n` | Number of recent runs to show (default: 20) |
| `--workflow` | `-w` | Filter by workflow name (substring match) |
| `--status` | `-s` | Filter by status: `completed`, `failed`, `canceled` |
| `--verbose` | `-v` | Show project, job count, and step count columns |
| `--clear` | | Delete all run history |
| `--prune N` | | Keep only the last N entries |

## Output

Default view:

```
         Run History (last 5)
 Run ID   Workflow         Status   Duration  Time
 a1b2c3d4 subdomain-recon  ✓ OK     12.5s    5m ago
 e5f6g7h8 port-blitz       ✗ FAIL    3.2s    15m ago
 i9j0k1l2 web-full-audit   ✓ OK      1.2m    1h ago
```

Verbose view (`-v`) adds project, jobs, and steps columns.

## Storage

History is stored in `~/.ofx/history/runs.ndjson` as append-only newline-delimited JSON. Each record contains:

- `run_id` — unique run identifier
- `workflow` — workflow name
- `status` — completion status
- `timestamp` — ISO 8601 timestamp
- `elapsed_seconds` — total duration
- `project` — project name (if used)
- `total_jobs` / `failed_jobs` — job counts
- `total_steps` / `failed_steps` — step counts

## Automatic Tracking

Every `ofx flow run` execution automatically records to history. No configuration needed.
