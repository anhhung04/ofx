# Quick Start

This quick start gets you from install to a successful workflow run.

## 1) Install OFX

```bash
pip install ofx
```

Optional cloud extras:

```bash
pip install "ofx[cloud]"
```

## 2) Create a project

```bash
ofx project init quickstart-demo
cd ~/.ofx/projects/quickstart-demo
```

## 3) Run a task directly

The fastest way to use OFX is running a task from the command line — no YAML needed:

```bash
# Port scan a target
ofx flow tasks run nmap 10.10.10.5 --opt ports=1-1000

# Probe HTTP services
ofx flow tasks run httpx example.com --opt tech_detect

# Subdomain enumeration
ofx flow tasks run subfinder example.com
```

## 4) Create a workflow

Create `recon.yml`:

```yaml
name: quick-recon

dispatch:
  inputs:
    target:
      type: string
      required: true
      description: Target to scan

jobs:
  scan:
    steps:
      # Task step — structured output parsing
      - task: nmap
        name: port-scan
        with:
          target: "{{ inputs.target }}"
          ports: "80,443,8080"

      # Shell command
      - name: show-results
        run: echo "Found {{ ports(steps['port-scan'].outputs.typed_outputs) | length }} open ports"

  analyze:
    needs: [scan]
    steps:
      # Inline Python script
      - name: summarize
        script: |
          import json
          result = {"target": "{{ inputs.target }}", "status": "complete"}
          with open("{{ ctx.output_path }}/summary.json", "w") as f:
            json.dump(result, f, indent=2)
          print(f"Summary saved to {{ ctx.output_path }}/summary.json")
```

## 5) Validate and run

```bash
ofx flow validate recon.yml
ofx flow run recon.yml --input target=10.10.10.5
```

## 6) Add secrets (optional)

```bash
ofx secret set API_KEY
```

Use in workflow:

```yaml
call:
  secrets:
    API_KEY:
      required: true
```

## 7) Useful next commands

```bash
ofx flow tasks list                          # See all 90+ built-in tasks
ofx flow tasks info nmap                     # Task options and details
ofx flow visualize recon.yml --format dot      # Render the DAG (DOT format)
ofx flow run recon.yml --output ./runs/recon  # Custom output directory
```

## What to read next

- [Tasks](../guide/tasks.md) — Pre-built security tool wrappers
- [Workflows](../guide/workflows.md) — Workflow structure and features
- [Jobs & Steps](../guide/jobs-steps.md) — Step types and configuration
- [Templates](../guide/templates.md) — Jinja2 helpers and functions
- [Secrets & Inputs](../guide/secrets-inputs.md) — Credential management
- [Cloud Runners](../guide/cloud-runners.md) — Remote execution
