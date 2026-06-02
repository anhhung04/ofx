# Run Command

> Execute OFX workflow files with inputs, secrets, and output options

---

## Usage

```bash
ofx flow run <workflow_name> [OPTIONS]
ofx x run <workflow_name> [OPTIONS]      # Shorthand alias
ofx task run <workflow_name> [OPTIONS]   # Another alias
```

---

## Options

| Option | Description |
|--------|-------------|
| `-i, --input key=value` | Set input variables (repeatable). Values are JSON-decoded when possible. |
| `-o, --output <dir>` | Output directory for artifacts (default: temp dir under `~/.ofx/tmp`) |
| `-p, --project <name>` | Run for a specific project. Sets output to `<project>/logs` and exposes project vars. |
| `--profile <name>` | Apply an execution profile (rate limits, stealth, time windows). See [Profiles](../../guide/profiles.md). |
| `--perf-profile` | Enable cProfile performance profiling and write `profile.prof` into the output directory. |
| `--dry-run` | Show execution plan without running (jobs, stages, inputs, dependencies) |
| `-T, --load-targets` | Load targets from project `targets/` folder and expand as matrix input |
| `--time-window HH:MM-HH:MM` | Restrict execution to a time window (e.g. `09:00-17:00`) |
| `--quiet` | Suppress interactive console output (cron/headless mode) |
| `--lock <path>` | Lock file path to prevent overlapping runs (cron-safe) |
| `--wait-lock <seconds>` | Seconds to wait for lock acquisition before failing (default: 0) |
| `--log-format <format>` | Log format: `rich` (default), `json`, or `text` |
| `--events/--no-events` | Emit structured lifecycle events to `<output>/events.ndjson` |
| `--durable/--no-durable` | Enable or disable durable execution checkpoints |
| `--resume/--no-resume` | Resume from last completed step when checkpoints exist |
| `--durable-backend <file\|redis>` | Durable backend to use |
| `--durable-redis-prefix <prefix>` | Redis key prefix for durable checkpoints |

---

## Examples

### Basic Run
```bash
ofx flow run recon --input target=example.com
```

### With Multiple Inputs
```bash
ofx flow run scan \
  --input target=10.0.0.1 \
  --input ports=22,80,443 \
  --input timeout=300
```

### Control Builtin Workflow Logging
```bash
ofx flow run full-recon \
  --input target=example.com \
  --input log_command=false \
  --input log_output=true
```

Many builtin workflows accept `log_command` and `log_output` as regular workflow inputs. When present, they control builtin step `log-command` and `log-stdout` behavior for that run, including recursive builtin subworkflows reached through `uses:`.

### Run for a Project
```bash
ofx flow run full-recon --project client-pentest --input target=10.0.0.0/24
```

Output is automatically saved to `<project>/logs` and project metadata (name, path) is available in templates via `{{ project_name }}` and `{{ project_path }}`.

### With Output Directory
```bash
ofx flow run exploit \
  --input target=10.0.0.1 \
  --output results/
```

### Quiet / Headless Mode
```bash
# Suitable for cron jobs — no interactive progress bars
ofx flow run nightly-scan --quiet --log-format json
```

### Lock File (Prevent Overlapping Runs)
```bash
# Only one instance at a time; others fail immediately
ofx flow run scan --lock /tmp/ofx-scan.lock

# Wait up to 60 seconds for lock
ofx flow run scan --lock /tmp/ofx-scan.lock --wait-lock 60
```

### Durable Execution (Resume)
```bash
ofx flow run scan \
  --output results/ \
  --durable \
  --resume
```

### Durable Execution with Redis
```bash
ofx flow run scan \
  --output results/ \
  --durable \
  --durable-backend redis \
  --durable-redis-prefix ofx:durable:
```

### Structured Event Stream (NDJSON)
```bash
ofx flow run scan --events --output results/
```

This writes newline-delimited JSON events to:

```text
results/events.ndjson
```

Each line contains runner lifecycle metadata (`event_type`, `runner_type`, `run_id`, status, timestamps, job/step context).

---

## Tips

- Use the `x` alias for faster typing: `ofx x run ...`
- Input values are JSON-decoded when possible — `--input count=5` sets an integer, `--input tags='["a","b"]'` sets a list
- Builtin workflows may expose runtime logging inputs such as `log_command` and `log_output`
- `--project` resolves the project via `ProjectManager` and injects project vars into the workflow context
- `--quiet` and `--log-format json` are ideal for CI/CD and cron jobs
- Outputs and logs are saved in the specified output directory
- Installed [collections](../../guide/collections.md) are automatically included in the workflow search path

---

## See Also

- [**Workflow Syntax**](../../guide/workflows.md) — Complete workflow reference
- [**Inputs & Secrets**](../../guide/secrets-inputs.md) — Managing inputs and secrets
- [**Templates**](../../guide/templates.md) — Jinja2 templating
- [**Collections**](../../guide/collections.md) — Installable workflow packages
