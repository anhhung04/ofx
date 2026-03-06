# Lifecycle & Cleanup

This page covers the full lifecycle of a cloud job — from provisioning to destruction — including what gets cleaned up, what happens on failure, and what you should verify after a run.

## Cloud Job Lifecycle

```
_pre_run                              _do_run                    _post_run
─────────────────────────────────     ─────────────────────     ──────────────────────────
1. Resolve cloud config/profile       5. Upload fleet input     8. Download outputs
2. Create VPS (provider API)          6. Execute steps via SSH  9. Destroy VPS
3. Wait for VPS ready + SSH/WinRM     7. Stream step output     10. Close SSH connection
4. Create remote working directory                              11. Remove remote work dir
```

### 1. Provisioning (`_pre_run`)

1. **Resolve cloud config** — merge profile base + inline overrides + CLI flags
2. **Register credentials for redaction** — SSH passwords, API tokens are added to the log redaction filter
3. **Check run_if conditions** — evaluate job dependencies
4. **Create VPS** via provider API (`create_instance`)
5. **Wait for VPS ready** — poll provider API until status is "active" and IP is assigned (`startup_timeout`, default 300s)
6. **Wait for SSH/WinRM port** — TCP connect to port 22/5985/5986 (`boot_timeout`, default 180s)
7. **Wait for login** — attempt real SSH/WinRM authentication until it succeeds (`login_timeout`, default 300s). This is separate because cloud-init may still be configuring users/keys after the port is open.
8. **Create remote runner** — instantiate `PostSSH` or `PostWinRM` with connection details
9. **Create remote work dir** — `mkdir -p /tmp/.run-{run_id[:8]}` on the VPS

### 2. Execution (`_do_run`)

1. **Upload fleet input** (if fleet job) — SCP chunk file to `<work_dir>/fleet_targets.txt`
2. **Execute steps sequentially** — each step is sent as a command over SSH/WinRM with:
   - Environment variable exports prepended
   - `cd <work_dir>` prefix
   - Timeout enforcement
   - Retry support (configurable per step)
3. **Stream output** — step stdout is captured and logged locally

### 3. Post-run (`_post_run`)

1. **Download outputs** — list files in `<work_dir>/output/` and SCP them to local output directory
2. **Destroy VPS** — call provider API to delete the instance (if `auto_destroy: true`)
3. **Close SSH/WinRM connection** — release paramiko/WinRM resources
4. **Remove remote work dir** — `rm -rf <work_dir>` (best-effort, runs before destroy)

## What Gets Cleaned Up

### On successful completion

| Item | Cleaned up? | How |
|------|-------------|-----|
| VPS instance | Yes (if `auto_destroy: true`) | Provider API `destroy_instance()` |
| Remote work dir (`/tmp/.run-*`) | Yes | `rm -rf` via SSH before destroy |
| SSH/WinRM connection | Yes | `PostSSH.cleanup()` |
| Local fleet chunk files | Yes | `CloudMatrixJobRunner._cleanup_chunk_files()` |
| Local output files | **Kept** | Downloaded to `<output_path>/<job_id>/` |
| Registry data | **Kept** | Job results, execution data, outputs |

### On failure

| Item | Cleaned up? | How |
|------|-------------|-----|
| VPS instance | **User prompt** | Interactive TTY: prompts "Destroy this instance? [y/N]". Non-TTY: left running with warning |
| Remote work dir | Best-effort | Cleaned during `_cleanup_remote()` |
| SSH/WinRM connection | Yes | Always cleaned up |
| Local fleet chunk files | Yes | Always cleaned up by `CloudMatrixJobRunner` |
| Output files produced before failure | **Salvaged** | Downloaded before prompting for destroy |

### Failure handling flow

```
Exception caught in CloudJobRunner.run()
  │
  ├── 1. Try to download outputs (salvage)
  │     └── If download fails, log debug message and continue
  │
  ├── 2. Check if VPS needs cleanup
  │     ├── Static provider → skip (never destroy static hosts)
  │     ├── TTY mode → prompt "Destroy this instance? [y/N]"
  │     │     ├── Yes → destroy VPS
  │     │     └── No → log warning with instance details
  │     └── Non-TTY mode → log warning with instance details
  │
  └── 3. Close SSH/WinRM transport
```

### Fleet failure handling

When a fleet job partially fails (some instances succeed, some fail):

1. Each child `CloudJobRunner` detects its own failure and salvages outputs (downloads files produced before the error)
2. Individual fleet children **do not** prompt about destruction — this is deferred to the parent
3. `CloudMatrixJobRunner` collects errors from all `asyncio.gather` results
4. Surviving instances (those that didn't auto-destroy) are listed with IP/ID/provider details
5. A **single consolidated prompt** asks the user whether to destroy all surviving fleet instances at once
6. In non-TTY mode (CI, sessions), instances are logged as warnings for manual cleanup
7. The error message lists all failed combinations: `"Combination 0: ...; Combination 1: ..."`

This design avoids concurrent `input()` calls that would garble the terminal when multiple fleet instances fail simultaneously.

## Remote Working Directory

Each cloud job creates a unique working directory on the VPS:

| OS | Path | Example |
|----|------|---------|
| Linux | `/tmp/.run-{run_id[:8]}` | `/tmp/.run-a1b2c3d4` |
| Windows | `C:\Windows\Temp\.run-{run_id[:8]}` | `C:\Windows\Temp\.run-a1b2c3d4` |

This directory is used for:

- Step execution (`cd <work_dir> && <command>`)
- Fleet input file upload (`<work_dir>/fleet_targets.txt`)
- Output file collection (`<work_dir>/output/`)
- Script file upload (for `script:` and `script_file:` steps)

Steps can create an `output/` subdirectory inside the work dir. Any files in `<work_dir>/output/` are automatically downloaded to local storage after the job completes.

## Output Collection

### How outputs are downloaded

After all steps complete:

1. OFX lists files in `<work_dir>/output/` on the VPS
2. Each file is downloaded via SFTP to `<local_output_path>/<job_id>/<filename>`
3. Subdirectories inside `output/` are not recursively downloaded (only top-level files)

### Output directory structure

```
/tmp/.tmp_r_.../run_<timestamp>/
├── fleet-scan_0/          # Job ID for fleet instance 0
│   ├── scan-0.gnmap
│   ├── scan-0.nmap
│   └── scan-0.xml
├── fleet-scan_1/          # Job ID for fleet instance 1
│   ├── scan-1.gnmap
│   ├── scan-1.nmap
│   └── scan-1.xml
└── logs/
    └── cloud_commands/    # If log_commands: true
        ├── fleet-scan_0_152.42.219.32.log
        └── fleet-scan_1_157.245.59.249.log
```

### Writing output from steps

To have files downloaded, write them to `output/` inside the working directory:

```yaml
steps:
  - run: |
      mkdir -p output
      nmap -sV target.com -oA output/scan
      echo "done" > output/status.txt
```

## VPS Destruction

### auto_destroy (default: true)

When `auto_destroy: true` (the default), the VPS is destroyed after successful completion:

```
Destroying instance 'ofx-sgp1-abc123'[556325872] (provider=digitalocean)
Destroyed DO droplet with id 556325872
```

Set `auto_destroy: false` to keep the VPS running after the job:

```yaml
jobs:
  persistent:
    cloud:
      profile: do-small
      auto_destroy: false
    steps:
      - run: ./setup-tool.sh
```

### Static provider

Static hosts are **never** destroyed, regardless of `auto_destroy` setting. Only SSH/WinRM connections are cleaned up.

### Manual destruction

If a VPS is left running (due to failure or `auto_destroy: false`):

```bash
# List running instances
ofx cloud instance list --provider digitalocean

# Destroy by ID
ofx cloud instance destroy 556325872 --provider digitalocean

# Destroy by tag (all OFX instances)
ofx cloud fleet destroy --prefix ofx --provider digitalocean
```

## What to Check After a Run

### After success

- Output files are in the local output directory
- All VPS instances should be destroyed (verify via cloud provider dashboard)
- Fleet chunk files should be cleaned up (check `/tmp/ofx_fleet_*`)

### After failure

1. **Check for orphaned VPS** — the failure log includes instance details:
   ```
   WARNING Cloud instances from failed combinations may still be running:
     fleet-scan_0: ofx-sgp1-abc [556325872] @ 152.42.219.32 (provider=digitalocean)
   ```
2. **Salvaged outputs** — check the local output directory for any files downloaded before failure
3. **Verify destruction** — if you answered "yes" to the destroy prompt, confirm via provider dashboard
4. **Review command logs** — if `log_commands: true`, check `logs/cloud_commands/` for the full SSH command history

### Cost control

- Always verify no orphaned instances exist after failed runs
- Use `tags: [ofx]` (added automatically) to find OFX instances in your cloud dashboard
- Set up cloud provider billing alerts
- Use `max_parallel` to limit concurrent VPS count
- Consider `auto_destroy: true` (the default) — only disable for debugging

## Python Script Steps on VPS

For `script:` and `script_file:` steps, OFX:

1. **Discovers Python** on the remote host (probes `python3`, `python`, and common absolute paths)
2. **Bundles OFX API dependencies** — analyzes imports, collects required `ofx.api` module sources
3. **Creates a self-extracting bootstrap** — base64-encoded zip of OFX modules + user script
4. **Uploads the bootstrap** to the VPS
5. **Executes** via the discovered Python interpreter
6. **Cleans up** the bootstrap file

This means `ofx.api` functions are available on the VPS without installing the OFX package:

```yaml
steps:
  - script: |
      from ofx.api.recon import nmap_scan
      cmd = nmap_scan("10.0.0.0/24", ports="1-1000")
      print(cmd)
```
