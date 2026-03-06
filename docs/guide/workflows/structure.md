# Workflow Structure

The core of an OFX workflow is defined in a single YAML file. Below is a minimal example that demonstrates all top‑level sections.

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

## Key Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | ✅ | Unique workflow identifier |
| `description` | ❌ | Human‑readable description |
| `tags` | ❌ | Tags for organizing workflows |
| `dispatch` | ❌ | Manual trigger inputs configuration (`inputs`) |
| `call` | ❌ | Reusable workflow configuration (`inputs`, `secrets`, `outputs`) |
| `env` | ❌ | Global environment variables |
| `tools` | ❌ | Tool installers for workflow runs |
| `defaults` | ❌ | Default run settings (shell, working directory, etc.) |
| `jobs` | ✅ | Map of jobs to execute |

These sections map directly to the data models under `src/ofx/models/workflow.py` and are parsed by the `WorkflowRunner` in `src/ofx/runner/execution/workflow.py`.

--- 

[← Back to Workflows Overview](../workflows.md)