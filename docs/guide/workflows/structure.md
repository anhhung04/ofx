# Workflow Structure

Every OFX workflow is a single YAML file with two required fields (`name` and `jobs`) and several optional sections for inputs, secrets, environment, tooling, and defaults.

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

tools:
  subfinder: go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest

defaults:
  shell: /bin/bash
  profile: stealth
  store-creds: true

outputs:
  result: "${{ jobs.scan.outputs.result }}"

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

## Top-Level Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | ✅ | Unique workflow identifier |
| `description` | ❌ | Human‑readable description (default: "No provided description") |
| `tags` | ❌ | Tags for organizing and searching workflows |
| `dispatch` | ❌ | Inputs for manual/CLI triggers |
| `call` | ❌ | Reusable workflow interface — `inputs`, `secrets`, and `outputs` |
| `env` | ❌ | Global environment variables available to all jobs |
| `tools` | ❌ | Tool installers run before any jobs execute |
| `defaults` | ❌ | Default settings: shell, working directory, profile, store-creds, durable config |
| `outputs` | ❌ | Workflow-level outputs mapped from job outputs |
| `jobs` | ✅ | Map of job IDs to job definitions |

---

## `dispatch` — Manual Trigger Inputs

Declare inputs that users provide when running the workflow:

```yaml
dispatch:
  inputs:
    target:
      required: true
      description: Target IP or domain
    ports:
      required: false
      description: Port range to scan
      default: "1-1000"
```

Pass values at runtime:

```bash
ofx flow run workflow.yml --input target=10.0.0.1 --input ports=80,443
```

Access in templates: `{{ inputs.target }}`, `{{ inputs.ports }}`

---

## `call` — Reusable Workflow Interface

When a workflow is invoked via `uses:` from another workflow, `call` defines what it accepts:

```yaml
call:
  inputs:
    target:
      required: true
  secrets:
    API_KEY:
      required: false
  outputs:
    result: "{{ jobs.scan.outputs.open_ports }}"
```

See [Reusable Workflows](reusable.md) for details.

---

## `tools` — Pre-Run Tool Installation

Install binaries into `~/Tools/bin` before jobs execute. Each entry is either a simple install command or a full config:

```yaml
tools:
  # Simple string form
  subfinder: go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest

  # Full config with check and post-install
  naabu:
    install: go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@latest
    check: naabu -version
    post_install: echo "naabu installed"
```

The `check` command verifies the tool is already installed (skips re-install if it succeeds). `post_install` runs after a successful install.

---

## `defaults` — Workflow-Wide Settings

Set defaults that cascade to all jobs and steps:

```yaml
defaults:
  shell: /bin/bash
  working-directory: /opt/scans
  profile: stealth              # Execution profile (rate limits, proxy, etc.)
  store-creds: true             # Auto-store UserAccount credentials from tasks
  durable:
    enabled: true
    resume: true
    backend: file
```

Job-level and step-level settings override these defaults.

---

## `outputs` — Workflow-Level Outputs

Promote job outputs for callers to access when this workflow is used as a reusable workflow:

```yaml
outputs:
  live_hosts: "${{ jobs.scan.outputs.live_hosts }}"
  vuln_count: "${{ jobs.vuln.outputs.vuln_count }}"
```

---

## Job ID Rules

Job IDs must match `[A-Za-z0-9_-]+`. Dependencies listed in `needs` must reference existing job IDs, and circular dependencies are rejected at parse time.

---

## Validation

Check a workflow for schema and dependency errors before running:

```bash
ofx flow validate workflow.yml
```

---

[← Back to Workflows Overview](../workflows.md)