# Basic Concepts

Essentials for writing OFX workflows.

## Workflow

- Top-level YAML: `name`, optional `description`, `inputs`, `secrets`, `jobs`, optional `hooks`.
- Keep IDs simple; use `needs` for ordering.

Example:
```yaml
name: workflow-name
jobs:
  recon:
    steps:
      - run: nmap -sV ${{ inputs.target }}
  exploit:
    needs: [recon]
    steps:
      - run: python exploit.py
```

## Job

- Runs steps sequentially; `needs` controls dependencies; can set env and hooks.
- Fail-fast unless steps set `continue_on_error`.

## Step

- Exactly one of `run`, `script`, `uses`.
- Key fields: `name`, `timeout`, `retry`/`retry_delay`, `continue_on_error`, `working_directory`, `env`.
- `script` runs Python code with access to workflow context and inter-job communication functions.

```yaml
- name: Bash command
  run: echo "Hello"
- name: Python with channels
  script: |
    publish('status', {'state': 'running'})
    data = wait_for('config', lambda d: d.get('ready'))
- name: Subflow
  uses: ./other.yml
```

## Inputs

- Defined under `inputs`; use via `${{ inputs.key }}`.
- Provide via CLI: `--input key=value` (JSON parsed when possible).
```yaml
inputs:
  target:
    required: true
    default: "127.0.0.1"
```

## Secrets

- Defined under `secrets`; use via `${{ secrets.KEY }}`.
- Provide with `--secret KEY=val` or store via `ofx secret set KEY`.

## Hooks

- Optional `hooks` at workflow/job/step; propagate downward.
- Common: `on_start`, `on_success`, `on_failure`, `before_step`, `after_step`.

## Templates

- Jinja2 `${{ ... }}` on strings/nums/bools/maps/lists.
- Variables: `inputs`, `secrets`, `envs`, `ctx` (run_id, output_path, workflow/job/step metadata).
- Helpers: `uv_install`, `go_install`, `npm_install`, `cargo_install`, `tools_dir`, `tools_bin_dir`, `file_read`, `file_write`.

## Dependencies

- Use `needs` to gate jobs; jobs without `needs` run in parallel.
```yaml
jobs:
  a:
    steps: [{ run: echo a }]
  b:
    needs: [a]
    steps: [{ run: echo b }]
```
```

### Execution Flow

```
recon ─┐
       ├─→ analyze
scan ──┘
```

Jobs `recon` and `scan` run in parallel (if possible), then `analyze` runs.

## Environment Variables

Define environment variables at different levels:

### Workflow Level

```yaml
name: Environment Variables Demo
envs:
  GLOBAL_VAR: "value"

jobs:
  job1:
    name: Use Global Env
    steps:
      - name: Print global variable
        run: echo $GLOBAL_VAR  # Available
```

### Job Level

```yaml
jobs:
  job1:
    envs:
      JOB_VAR: "value"
    steps:
      - run: echo $JOB_VAR  # Available
```

### Step Level

```yaml
steps:
  - name: With env
    envs:
      STEP_VAR: "value"
    run: echo $STEP_VAR
```

## Error Handling

Control error behavior at different levels:

### Continue on Error

```yaml
jobs:
  resilient:
    continue_on_error: true  # Job continues even if step fails
    steps:
      - run: false  # Fails but job continues
      - run: echo "Still runs"
```

### Retry Configuration

```yaml
steps:
  - name: Flaky command
    retry:
      max_attempts: 3
      delay: 5  # seconds
    run: curl https://api.example.com
```

### Timeout

```yaml
steps:
  - name: Long task
    timeout: 300  # 5 minutes
    run: long-running-command
```

## Output Management

Control where outputs are saved:

### Output Directory

```yaml
# Set at workflow level
output_dir: "./results"

jobs:
  scan:
    steps:
      - run: nmap -oN output.txt ${{ inputs.target }}
        # Saves to ./results/output.txt
```

### Custom Output Path

```bash
# From CLI
ofx flow run scan --output /tmp/scan-results
```

### Accessing Outputs

```yaml
steps:
  - name: Save results
    run: echo "Results" > ${{ output_path('data.txt') }}
  
  - name: Read results
    run: cat ${{ output_path('data.txt') }}
```

## Context Variables

Access runtime information via `ctx`:

### Workflow Context

```yaml
${{ ctx.workflow.name }}        # Workflow name
${{ ctx.workflow.description }} # Description
```

### Job Context

```yaml
${{ ctx.job.name }}             # Current job name
${{ ctx.job.id }}               # Job ID
```

### Step Context

```yaml
${{ ctx.step.name }}            # Current step name
${{ ctx.step.index }}           # Step number
```

### System Context

```yaml
${{ ctx.system.os }}            # Operating system
${{ ctx.system.arch }}          # Architecture
${{ ctx.system.user }}          # Current user
```

## Best Practices

### 1. Use Descriptive Names

**Good:**
```yaml
name: comprehensive-web-app-security-scan
jobs:
  subdomain-enumeration:
    steps:
      - name: Run subfinder for subdomain discovery
```

**Bad:**
```yaml
name: scan
jobs:
  job1:
    steps:
      - name: step1
```

### 2. Validate Inputs

```yaml
inputs:
  target:
    description: Target domain (e.g., example.com)
    required: true
  
  timeout:
    description: Scan timeout in seconds
    default: 300
```

### 3. Use Hooks for Logging

```yaml
hooks:
  on_start:
    - run: echo "=== Scan started at $(date) ==="
  on_success:
    - run: echo "=== Scan completed at $(date) ==="
  on_failure:
    - run: echo "=== Scan failed at $(date) ===" >&2
```

### 4. Organize with Dependencies

```yaml
jobs:
  setup:
    steps:
      - run: mkdir -p results
  
  scan:
    needs: [setup]
    steps:
      - run: nmap -oN results/nmap.txt target
  
  cleanup:
    needs: [scan]
    steps:
      - run: tar -czf results.tar.gz results/
```

### 5. Handle Errors Gracefully

```yaml
steps:
  - name: Optional step
    continue_on_error: true
    run: experimental-tool
  
  - name: Critical step
    retry:
      max_attempts: 3
    run: important-command
```

## Next Steps

- [Workflows](../guide/workflows.md) - Comprehensive workflow guide
- [Jobs & Steps](../guide/jobs-steps.md) - Job and step configuration
- [Hooks](../guide/hooks.md) - Hook system deep dive
- [Templates](../guide/templates.md) - Template syntax and functions
- [API Overview](../api/overview.md) - Red teaming APIs
