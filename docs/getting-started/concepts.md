# Core Concepts

> Essential building blocks for writing OFX workflows

---

## 🏗️ Workflow Structure

A workflow is a YAML file with these key sections:

```yaml
name: my-workflow
description: Optional description

inputs:          # User-provided parameters
  target:
    required: true

secrets:         # Secure credentials
  API_KEY:
    required: false

jobs:            # Execution units
  scan:
    steps:
      - run: nmap -sV {{ inputs.target }}

hooks:           # Lifecycle events (optional)
  on_success:
    - run: echo "Done"
```

---

## 📦 Jobs

Jobs are independent execution units that can run in parallel.

| Property | Description |
|----------|-------------|
| `steps` | List of steps to execute sequentially |
| `needs` | Dependencies on other jobs |
| `envs` | Environment variables for all steps |
| `continue_on_error` | Don't stop on failure |
| `hooks` | Job-level lifecycle events |

```yaml
jobs:
  recon:
    steps:
      - run: nmap -sV {{ inputs.target }}
  
  exploit:
    needs: [recon]  # Waits for recon to complete
    steps:
      - run: python exploit.py
```

---

## 📝 Steps

Steps execute commands within a job. Each step uses exactly **one** of:

| Type | Description |
|------|-------------|
| `run` | Shell command |
| `script` | Python code |
| `uses` | Subflow reference |

### Step Properties

| Property | Description |
|----------|-------------|
| `name` | Descriptive step name |
| `timeout` | Max execution time (seconds) |
| `retry` | Retry attempts on failure |
| `retry_delay` | Delay between retries |
| `continue_on_error` | Continue on failure |
| `working_directory` | Execution directory |
| `envs` | Step environment variables |

### Examples

```yaml
steps:
  # Shell command
  - name: Scan ports
    run: nmap -sS {{ inputs.target }}
    timeout: 300

  # Python script
  - name: Process results
    script: |
      publish('status', {'state': 'running'})
      data = wait_for('config', lambda d: d.get('ready'))

  # Subflow
  - name: Run recon module
    uses: ./recon.yml
```

---

## 📥 Inputs

Define parameters users can provide at runtime:

```yaml
inputs:
  target:
    required: true
    description: Target host or IP
  
  ports:
    default: "80,443"
    description: Ports to scan
```

**Usage in templates:** `{{ inputs.target }}`

**CLI:** `ofx flow run scan --input target=example.com --input ports=22,80`

---

## 🔐 Secrets

Secure credentials that are masked in logs:

```yaml
secrets:
  API_KEY:
    required: true
    description: API authentication key
```

**Usage:** `{{ secrets.API_KEY }}`

**Set secrets:**
```bash
ofx secret set API_KEY
# Or via CLI: --secret API_KEY=value
```

---

## 🔗 Job Dependencies

Control execution order with `needs`:

```yaml
jobs:
  a:
    steps: [{ run: echo "A" }]
  
  b:
    needs: [a]  # Runs after A
    steps: [{ run: echo "B" }]
  
  c:
    needs: [a]  # Also runs after A (parallel with B)
    steps: [{ run: echo "C" }]
```

**Execution flow:**
```
     ┌─→ B
A ───┤
     └─→ C
```

> Jobs without `needs` run in parallel when possible.

---

## 🌍 Environment Variables

Set environment variables at different scopes:

### Workflow Level
```yaml
envs:
  GLOBAL_VAR: "value"

jobs:
  job1:
    steps:
      - run: echo $GLOBAL_VAR  # Available everywhere
```

### Job Level
```yaml
jobs:
  job1:
    envs:
      JOB_VAR: "value"
    steps:
      - run: echo $JOB_VAR  # Available in this job
```

### Step Level
```yaml
steps:
  - name: With custom env
    envs:
      STEP_VAR: "value"
    run: echo $STEP_VAR  # Available in this step only
```

---

## ⚠️ Error Handling

### Continue on Error
```yaml
jobs:
  resilient:
    continue_on_error: true
    steps:
      - run: may-fail-command
      - run: echo "Still runs even if above fails"
```

### Retry on Failure
```yaml
steps:
  - name: Flaky API call
    run: curl https://api.example.com
    retry: 3
    retry_delay: 5  # seconds
```

### Timeout
```yaml
steps:
  - name: Long operation
    run: long-running-command
    timeout: 300  # 5 minutes
```

---

## 📄 Context Variables

Access runtime information via `ctx`:

| Variable | Description |
|----------|-------------|
| `ctx.run_id` | Unique run identifier |
| `ctx.output_path` | Output directory |
| `ctx.workflow.name` | Workflow name |
| `ctx.job.name` | Current job name |
| `ctx.step.name` | Current step name |
| `ctx.step.index` | Step number |
| `ctx.system.os` | Operating system |
| `ctx.system.user` | Current user |

```yaml
- run: echo "Run ID: {{ ctx.run_id }}"
- run: cp results.txt {{ ctx.output_path }}/
```

---

## 🪝 Hooks

Execute actions at lifecycle events:

| Hook | When |
|------|------|
| `on_start` | Before execution begins |
| `on_success` | After successful completion |
| `on_failure` | After failure |
| `before_step` | Before each step |
| `after_step` | After each step |

```yaml
hooks:
  on_start:
    - run: echo "🚀 Starting at $(date)"
  on_success:
    - run: echo "✅ Completed"
  on_failure:
    - run: echo "❌ Failed" >&2
```

---

## ✅ Best Practices

### Use Descriptive Names
```yaml
# ✅ Good
name: comprehensive-web-app-security-scan
jobs:
  subdomain-enumeration:
    steps:
      - name: Run subfinder for subdomain discovery

# ❌ Bad
name: scan
jobs:
  job1:
    steps:
      - name: step1
```

### Document Inputs
```yaml
inputs:
  target:
    description: Target domain (e.g., example.com)
    required: true
  
  timeout:
    description: Scan timeout in seconds
    default: 300
```

### Use Dependencies for Organization
```yaml
jobs:
  setup:
    steps: [{ run: mkdir -p results }]
  
  scan:
    needs: [setup]
    steps: [{ run: nmap -oN results/scan.txt target }]
  
  cleanup:
    needs: [scan]
    steps: [{ run: tar -czf results.tar.gz results/ }]
```

---

## ➡️ Next Steps

- [**Workflows**](../guide/workflows.md) — Complete workflow reference
- [**Jobs & Steps**](../guide/jobs-steps.md) — Detailed configuration
- [**Templates**](../guide/templates.md) — Jinja2 templating & helpers
- [**Hooks**](../guide/hooks.md) — Lifecycle system
- [**API Overview**](../api/overview.md) — Python API
