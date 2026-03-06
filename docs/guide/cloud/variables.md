# Variables & Environment in Cloud Jobs

Cloud jobs run on remote VPS instances, so passing variables, environment, and secrets works differently from local jobs. This page explains exactly what is available in templates, what environment variables reach the VPS, and how secrets are handled.

## Template Variables

Template variables are resolved **locally** before commands are sent to the VPS. When you write `{{ matrix.tool }}` in a step's `run:` field, OFX resolves it to the actual value, then sends the resolved command string over SSH/WinRM.

### Available template contexts

| Context | Access | Available in | Description |
|---------|--------|--------------|-------------|
| `inputs` | `{{ inputs.name }}` | All jobs | Workflow dispatch/call inputs |
| `secrets` | `{{ secrets.KEY }}` | All jobs | Values from OFX secret store |
| `matrix` | `{{ matrix.var }}` | Matrix/fleet jobs | Current matrix combination values |
| `fleet` | `{{ fleet.fleet_index }}` | Fleet jobs | Fleet-specific variables (alias for matrix fleet vars) |
| `strategy` | `{{ strategy.max_parallel }}` | Matrix/fleet jobs | Full strategy configuration |
| `env` | `{{ env.VAR }}` | All jobs | Workflow/job-level environment variables |
| `jobs` | `{{ jobs.job_id.outputs.key }}` | Jobs with `needs` | Outputs from dependency jobs |

### Matrix variables

When a job has `strategy.matrix`, each combination's values are accessible as `{{ matrix.<key> }}`:

```yaml
jobs:
  scan:
    cloud: do-small
    strategy:
      matrix:
        tool: [nmap, masscan]
        target: [10.0.0.0/24, 192.168.1.0/24]
    steps:
      - run: "{{ matrix.tool }} {{ matrix.target }}"
      # Resolves to: "nmap 10.0.0.0/24" (for combination 0)
```

### Fleet variables

Fleet jobs inject these variables into both the `matrix` and `fleet` contexts:

| Variable | Template access | Description |
|----------|-----------------|-------------|
| `fleet_index` | `{{ matrix.fleet_index }}` or `{{ fleet.fleet_index }}` | 0-based instance index |
| `fleet_total` | `{{ matrix.fleet_total }}` or `{{ fleet.fleet_total }}` | Total number of fleet instances |
| `fleet_input_file` | `{{ matrix.fleet_input_file }}` or `{{ fleet.fleet_input_file }}` | **Remote** path to this instance's target chunk file |
| `fleet_target_count` | `{{ matrix.fleet_target_count }}` or `{{ fleet.fleet_target_count }}` | Number of targets in this chunk |

**Important:** `fleet_input_file` in templates resolves to the **remote** path on the VPS (e.g. `/tmp/.run-abcd1234/fleet_targets.txt`), not the local temp file. OFX automatically uploads the chunk file to the VPS before step execution.

### Strategy variables

The full strategy config is available as `{{ strategy }}`:

```yaml
steps:
  - run: echo "Running {{ matrix.fleet_index }} of {{ strategy.fleet.count }}"
```

### Combined matrix + fleet

When using both `strategy.matrix` and `strategy.fleet`, the Cartesian product is created. All variables from both are merged into the `matrix` context:

```yaml
jobs:
  scan:
    cloud: do-small
    strategy:
      matrix:
        tool: [nmap, masscan]
      fleet:
        count: 3
        input: targets.txt
    steps:
      # 2 tools x 3 fleet chunks = 6 VPS instances
      - run: "{{ matrix.tool }} -iL {{ matrix.fleet_input_file }}"
```

## Environment Variables on VPS

Environment variables are **not** automatically inherited from your local machine. The VPS gets a clean environment. Only explicitly configured env vars are exported.

### How env vars reach the VPS

Env vars are prepended as `export` statements to each remote command:

```
export FLEET_INPUT_FILE="/tmp/.run-abc/fleet_targets.txt" && export MY_VAR="value" && cd /tmp/.run-abc && your-command-here
```

### Env var sources (in priority order, later overrides earlier)

| Source | Scope | Example |
|--------|-------|---------|
| Fleet vars (`FLEET_*`) | Auto-injected for fleet jobs | `FLEET_INPUT_FILE`, `FLEET_INDEX`, `FLEET_TOTAL`, `FLEET_TARGET_COUNT` |
| Job-level `env:` | All steps in the job | `env: { THREADS: "50" }` |
| Step-level `env:` | Single step only | `env: { TIMEOUT: "300" }` |

### Example: env at different levels

```yaml
jobs:
  scan:
    cloud: do-small
    env:
      THREADS: "50"           # Available in all steps
      SCAN_TYPE: "full"
    steps:
      - name: install
        run: apt install nmap -y

      - name: scan
        env:
          OUTPUT_DIR: "/tmp/results"   # Only this step
        run: |
          nmap -T4 --min-rate $THREADS -oA $OUTPUT_DIR/scan target.com
```

### Fleet env vars

Fleet jobs automatically export these environment variables for the remote cloud instances (uppercase versions of fleet context vars prefixed with `REMOTE_`):

| Env var | Value example | Description |
|---------|---------------|-------------|
| `REMOTE_FLEET_INPUT_FILE` | `/tmp/.run-abc/fleet_targets.txt` | Remote path to target chunk |
| `REMOTE_FLEET_INDEX` | `0` | Instance index |
| `REMOTE_FLEET_TOTAL` | `5` | Total fleet instances |
| `REMOTE_FLEET_TARGET_COUNT` | `42` | Targets in this chunk |

These are usable directly in shell commands without Jinja templates:

```yaml
steps:
  - run: |
      nmap -iL $REMOTE_FLEET_INPUT_FILE -oA output/scan-$REMOTE_FLEET_INDEX
```

### What is NOT exported to VPS

- Your local `PATH`, `HOME`, `USER`, etc.
- Local environment variables not in `env:` fields
- OFX internal variables (`OFX_DEBUG`, etc.)
- Secret values (see below)

## Secrets in Cloud Jobs

### How secrets are loaded

OFX performs **selective secret loading** — only secrets actually referenced in the workflow YAML are loaded from the encrypted store. This prevents unnecessary secret exposure.

References detected:

| Pattern | Example |
|---------|---------|
| Dot access | `{{ secrets.API_KEY }}` |
| Bracket access | `{{ secrets['API_KEY'] }}` |
| Call secret declarations | `call.secrets` field in reusable workflows |

### Using secrets in cloud steps

Secrets are resolved **locally** during template expansion, before the command is sent to the VPS:

```yaml
jobs:
  scan:
    cloud: do-small
    steps:
      - run: |
          # {{ secrets.SHODAN_KEY }} is replaced with the actual value locally
          # The resolved command is then sent over SSH
          shodan search --key {{ secrets.SHODAN_KEY }} apache
```

**Security note:** The resolved secret value **is** sent to the VPS as part of the command string. It will appear in the shell history on the VPS. To mitigate this:

1. Use `opsec_mode: true` — commands are written to a temp file and executed, reducing shell history exposure
2. The VPS is destroyed after the job (if `auto_destroy: true`), removing any traces
3. Use env vars instead of inline secrets for long-lived instances

### Passing secrets as environment variables

To export secrets as env vars on the VPS, reference them in the job's `env:` block:

```yaml
jobs:
  scan:
    cloud: do-small
    env:
      API_KEY: "{{ secrets.API_KEY }}"
      DB_PASSWORD: "{{ secrets.DB_PASSWORD }}"
    steps:
      - run: |
          # Available as $API_KEY on the VPS
          curl -H "Authorization: Bearer $API_KEY" https://api.example.com
```

### Log redaction

All secret values are automatically redacted from log output. Even with `OFX_DEBUG=1`, secrets appear as `***` in console output. Additionally, cloud credentials (SSH passwords, API tokens) are registered with the redaction filter automatically.

Redacted patterns include env var names containing: `password`, `passwd`, `secret`, `token`, `api_key`, `private_key`, `credential`, `auth`, `bearer`, `access_key`, `ssh_key`, `ssh_pass`.

### Secrets in reusable workflows

When a cloud job is part of a reusable workflow (`call:`), secrets declared in `call.secrets` are also loaded and registered for redaction:

```yaml
# parent.yml
jobs:
  scan:
    uses: child.yml
    with:
      target: example.com
    secrets:
      API_KEY: "{{ secrets.MAIN_API_KEY }}"
```

## Template vs Shell Variable Syntax

A common point of confusion — know the difference:

| Syntax | Resolved by | When | Example |
|--------|------------|------|---------|
| `{{ matrix.tool }}` | OFX (Jinja2) | Before sending to VPS | Becomes literal string in command |
| `$REMOTE_FLEET_INPUT_FILE` | Shell (bash) | On the VPS at runtime | Read from exported env var |
| `${{ strategy.fleet.count }}` | OFX (Jinja2) | Before sending to VPS | Alternative Jinja syntax |

**Rule of thumb:** Use `{{ }}` for values that OFX knows (matrix, secrets, inputs). Use `$VAR` for env vars that are exported to the VPS shell.

```yaml
steps:
  - run: |
      # Jinja template — resolved locally before SSH
      echo "Fleet instance {{ matrix.fleet_index }} of {{ matrix.fleet_total }}"

      # Shell variable — resolved on VPS at runtime
      nmap -iL $REMOTE_FLEET_INPUT_FILE -oA output/scan-$REMOTE_FLEET_INDEX

      # Both work for fleet vars. Use whichever you prefer:
      # {{ matrix.remote_fleet_input_file }} == $REMOTE_FLEET_INPUT_FILE
```
