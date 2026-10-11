# Core Concepts

> Essential building blocks for writing OFX workflows

---

## 🏗️ Workflow Structure

A workflow is a YAML file with these key sections:

```yaml
name: my-workflow
description: Optional description

dispatch:
  inputs:          # User-provided parameters
    target:
      required: true

call:
  secrets:         # Secure credentials
    API_KEY:
      required: false

jobs:            # Execution units
  scan:
    steps:
      - module: shell
        with:
          cmd: nmap -sV {{ inputs.target }}
```

---

## 📦 Jobs

Jobs are independent execution units that can run in parallel.

| Property | Description |
|----------|-------------|
| `steps` | List of steps to execute sequentially |
| `needs` | Dependencies on other jobs |
| `if` | Conditional execution |
| `strategy` | Matrix strategy configuration |
| `env` | Environment variables for all steps |
| `outputs` | Job outputs (template-resolved) |
| `cloud` | Cloud VPS configuration (profile name or inline config) |

```yaml
jobs:
  recon:
    steps:
      - module: shell
        with:
          cmd: nmap -sV {{ inputs.target }}
  
  exploit:
    needs: [recon]  # Waits for recon to complete
    steps:
      - module: shell
        with:
          cmd: python exploit.py
```

---

## 📝 Steps

Steps execute commands within a job. Each step uses exactly **one** of:

| Type | Description |
|------|-------------|
| `module: shell` | Shell command (`with.cmd`) |
| `module: python` | Python code (`with.script`) or file (`with.script_file`) |
| `module: <file>::<func>` | User-defined function module |
| `uses` | Subflow reference |
| `pipe` | Declarative ETL pipeline |

### Step Properties

| Property | Description |
|----------|-------------|
| `name` | Descriptive step name |
| `timeout` | Max execution time (minutes) |
| `retry` | Retry attempts on failure |
| `retry-delay` | Delay between retries |
| `continue-on-error` | Continue on failure |
| `working-directory` | Execution directory |
| `env` | Step environment variables |
| `store-creds` | Auto-store discovered credentials from module outputs |

### Examples

```yaml
steps:
  # Shell command
  - name: Scan ports
    module: shell
    with:
      cmd: nmap -sS {{ inputs.target }}
    timeout: 300

  # Python script
  - name: Process results
    module: python
    with:
      script: |
        publish('status', {'state': 'running'})
        data = wait_for('config', lambda d: d.get('ready'))

  # Subflow
  - name: Run recon module
    uses: ./recon.yml

Reusable workflows can be referenced by:
- Local path (relative or absolute)
- Workflow name in search paths
- Remote HTTP/HTTPS URL to a workflow file
- Git repository (e.g., `https://github.com/user/repo` or `github.com/user/repo`)
```

---

## 📥 Inputs

Define parameters users can provide at runtime:

```yaml
dispatch:
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
call:
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
    steps: [{ module: shell, with: {cmd: echo "A"} }]
  
  b:
    needs: [a]  # Runs after A
    steps: [{ module: shell, with: {cmd: echo "B"} }]
  
  c:
    needs: [a]  # Also runs after A (parallel with B)
    steps: [{ module: shell, with: {cmd: echo "C"} }]
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
env:
  GLOBAL_VAR: "value"

jobs:
  job1:
    steps:
      - module: shell
        with:
          cmd: echo $GLOBAL_VAR  # Available everywhere
```

### Job Level
```yaml
jobs:
  job1:
    env:
      JOB_VAR: "value"
    steps:
      - module: shell
        with:
          cmd: echo $JOB_VAR  # Available in this job
```

### Step Level
```yaml
steps:
  - name: With custom env
    env:
      STEP_VAR: "value"
    module: shell
    with:
      cmd: echo $STEP_VAR  # Available in this step only
```

---

## ⚠️ Error Handling

### Continue on Error
```yaml
jobs:
  resilient:
    steps:
      - module: shell
        with:
          cmd: may-fail-command
        continue-on-error: true
      - module: shell
        with:
          cmd: echo "Still runs even if above fails"
```

### Retry on Failure
```yaml
steps:
  - name: Flaky API call
    module: shell
    with:
      cmd: curl https://api.example.com
    retry: 3
    retry-delay: 5  # seconds
```

### Timeout
```yaml
steps:
  - name: Long operation
    module: shell
    with:
      cmd: long-running-command
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
- module: shell
  with:
    cmd: 'echo "Run ID: {{ ctx.run_id }}"'
- module: shell
  with:
    cmd: cp results.txt {{ ctx.output_path }}/
```

---

## ✅ Best Practices

### Use Descriptive Names
```yaml
# ✅ Good
name: recon-pipeline
jobs:
  subdomain-discovery:
    steps:
      - name: Run subfinder for subdomain discovery
        module: shell
        with:
          cmd: subfinder -d {{ inputs.target }}

# ❌ Bad
name: scan
jobs:
  job1:
    steps:
      - name: step1
        module: shell
        with:
          cmd: subfinder -d {{ inputs.target }}
```

### Document Inputs
```yaml
dispatch:
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
    steps: [{ module: shell, with: {cmd: mkdir -p results} }]
  
  scan:
    needs: [setup]
    steps: [{ module: shell, with: {cmd: nmap -oN results/scan.txt target} }]
  
  cleanup:
    needs: [scan]
    steps: [{ module: shell, with: {cmd: tar -czf results.tar.gz results/} }]
```

---

## ➡️ Next Steps

- [**Workflows**](../guide/workflows.md) — Complete workflow reference
- [**Jobs & Steps**](../guide/jobs-steps.md) — Detailed configuration
- [**Templates**](../guide/templates.md) — Jinja2 templating & helpers
- [**API Overview**](../api/overview.md) — Python API
