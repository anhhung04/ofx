# Workflows

> Complete guide to OFX workflow structure and configuration

---

## 📋 Workflow Structure

```yaml
name: my-workflow
description: Optional description
tags: [security, reconnaissance]

dispatch:
  inputs:
    target:
      required: true
      description: Target host

call:
  secrets:
    API_KEY:
      required: false

env:
  GLOBAL_VAR: "value"

jobs:
  scan:
    steps:
      - run: nmap -sV {{ inputs.target }}
  
  analyze:
    needs: [scan]
    steps:
      - run: python analyze.py

```

---

## 🔧 Key Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | ✅ | Unique workflow identifier |
| `description` | ❌ | Human-readable description |
| `tags` | ❌ | Tags for organizing workflows |
| `dispatch` | ❌ | Manual trigger inputs configuration (`inputs`) |
| `call` | ❌ | Reusable workflow configuration (`inputs`, `secrets`, `outputs`) |
| `env` | ❌ | Global environment variables |
| `tools` | ❌ | Tool installers for workflow runs |
| `defaults` | ❌ | Default run settings (shell, working directory, etc.) |
| `jobs` | ✅ | Map of jobs to execute |

---

## 🧱 Durable Execution

Enable durable checkpoints and resume behavior under `defaults.durable`:

```yaml
defaults:
  durable:
    enabled: true
    resume: true
    backend: file   # file or redis
    redis_prefix: ofx:durable:
```

**Notes:**
- Durable checkpoints are stored per run output directory when using the file backend.
- Use `backend: redis` to centralize checkpoints in Redis for multi-runner environments.

---

## ▶️ Running Workflows

```bash
# Validate first
ofx flow validate my-workflow

# Run with inputs
ofx flow run my-workflow --input target=example.com

# Run with secrets
ofx flow run my-workflow --secret API_KEY=xxx

# Combined
ofx flow run my-workflow \
  --secret API_KEY=xxx
```

---

## 📂 Workflow Sources

### Local Files
# Current directory
ofx flow run my-workflow.yml

# Absolute path
ofx flow run /path/to/workflow.yml

# From workflow directories (~/.ofx/workflows)
ofx flow run my-workflow
```

### Git Repositories
```bash
# Clone and run main workflow
ofx flow run https://github.com/user/repo

ofx flow run https://github.com/user/repo/workflows/scan.yml
```

### HTTP/HTTPS URLs
```bash
ofx flow run https://example.com/workflows/security-scan.yml
```

### S3 Buckets
```bash
ofx flow run s3://my-bucket/workflows/scan.yml

# With AWS credentials
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
ofx flow run s3://my-bucket/workflow.yml
```

> **Requirements:** boto3, AWS credentials, S3 read permissions


## 🔁 Reusable Workflows (`uses`)

Steps with `uses:` can reference reusable workflows using the same discovery logic as `ofx flow run`:

- Local file path (relative or absolute)
- Workflow name in search paths
- Remote HTTP/HTTPS URL to a workflow file
- Git repository (e.g., `https://github.com/user/repo` or `github.com/user/repo`)

---


Control execution order with `needs`:

```yaml
jobs:
  a:
  
  b:
    needs: [a]
    steps: [{ run: echo "B" }]
  
  c:
    needs: [a]
    steps: [{ run: echo "C" }]
```

**Execution flow:**
```
     ┌─→ B
A ───┤
     └─→ C
```


---

---

## 📝 Template Variables

Use Jinja2 templates with `{{ }}` syntax:

```yaml
jobs:
  scan:
    steps:
      - name: Scan target
        run: nmap -p {{ inputs.ports }} {{ inputs.target }}
      
      - name: Save results
        run: cp results.txt {{ ctx.output_path }}/scan_{{ ctx.run_id }}.txt
```

| Variable | Description |
| `{{ inputs.name }}` | Input value |
| `{{ secrets.name }}` | Secret value |
| `{{ ctx.output_path }}` | Output directory |
| `{{ ctx.run_id }}` | Unique run ID |
| `{{ tools_dir }}` | Tool installation directory |
| `{{ tools_bin_dir }}` | Tool binaries directory |
| `{{ local_ip() }}` | Local IP address |
| `{{ random_port() }}` | Random port number |

See [Templates](templates.md) for all available functions.
---

## 📁 Output Management

Workflows automatically create output directories:

```yaml
jobs:
  scan:
    steps:
```

**Output structure:**
```
output/
└── <run_id>/
    └── scan.xml
```

**Custom output path:**
```bash
ofx flow run scan --output /tmp/scan-results

---

## ⚠️ Error Handling

### Continue on Error
```yaml
jobs:
  scan:
    continue_on_error: true
    steps:
      - run: may-fail-command
      - run: echo "Still runs"

### Retry Logic
```yaml
steps:
  - name: API call
    run: curl https://api.example.com
    retry: 3
    retry_delay: 5  # seconds
```


## ✅ Best Practices

description: Comprehensive security assessment
```

### 2. Document Inputs
```yaml
dispatch:
  inputs:
    target:
      description: Target hostname or IP (e.g., example.com)
      required: true
    
    scan_type:
      description: "Scan type: quick, standard, comprehensive"
      default: "standard"
```

### 3. Validate Inputs Early
```yaml
jobs:
  validate:
    steps:
      - name: Check target format
        run: |
          if [[ ! "{{ inputs.target }}" =~ ^[a-zA-Z0-9.-]+$ ]]; then
            echo "Invalid target format" && exit 1
          fi
  
  scan:
    needs: [validate]
    steps:
      - run: nmap {{ inputs.target }}
```



---

## 📖 Examples

### Simple Scan
```yaml
name: port-scan
dispatch:
  inputs:
    target: { required: true }

jobs:
  scan:
    steps:
      - run: nmap -sS {{ inputs.target }}
      - run: nmap -sV {{ inputs.target }}
```

### Full Assessment
```yaml
name: security-assessment
dispatch:
  inputs:
    target: { required: true, description: Target network }
    depth: { default: "3", description: "Assessment depth (1-5)" }

call:
  secrets:
    SHODAN_KEY: { description: Shodan API key }

jobs:
  passive_recon:
    steps:
      - run: python osint.py --target {{ inputs.target }}
      - run: |
          {% if secrets.SHODAN_KEY %}
          shodan host {{ inputs.target }}
          {% endif %}

  active_scan:
    needs: [passive_recon]
    steps:
      - run: nmap -sS -sV -p- {{ inputs.target }}
      - run: nmap --script vuln {{ inputs.target }}

  analysis:
    needs: [active_scan]
    steps:
      - run: python analyze.py --input {{ ctx.output_path }}/scan.xml
      - run: python report.py --output {{ ctx.output_path }}/report.pdf
```

---

## 🐍 Python API

```python
import asyncio
import yaml
from pathlib import Path
from ofx.runner import WorkflowRunner, RunContext
from ofx.models.workflow import Workflow

async def main():
    data = yaml.safe_load(Path("workflow.yml").read_text())
    wf = Workflow(**data)
    result = await WorkflowRunner(wf, RunContext()).run()
    print(result.status)

asyncio.run(main())
```

---

## ➡️ See Also

- [**Jobs & Steps**](jobs-steps.md) — Detailed configuration
- [**Templates**](templates.md) — Template functions
- [**Secrets & Inputs**](secrets-inputs.md) — Credential management
