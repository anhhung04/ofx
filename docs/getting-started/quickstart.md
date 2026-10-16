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

## 3) Install your tools

Install the tools your workflow needs (see `ofx flow tools`):

```bash
# Install tool dependencies for a workflow
ofx flow tools my-recon.yml

# Or for all workflows
ofx flow tools --all
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
      # Shell module — run the scanner
      - name: port-scan
        module: shell
        with:
          cmd: nmap -p 80,443,8080 -oG - {{ inputs.target }}

      # Python module — parse scan output into typed outputs
      - name: parse-ports
        module: python
        with:
          script: |
            import re
            ports = []
            for line in """{{ steps['port-scan'].stdout }}""".splitlines():
                m = re.match(r'^(\S+)\s+(\d+)/open', line)
                if m:
                    ports.append({'_type': 'port', 'host': m.group(1), 'port': int(m.group(2))})
            add_outputs(typed_outputs=ports)

      # Shell command
      - name: show-results
        module: shell
        with:
          cmd: echo "Found {{ ports(steps['parse-ports'].outputs.typed_outputs) | length }} open ports"

  analyze:
    needs: [scan]
    steps:
      # Inline Python module
      - name: summarize
        module: python
        with:
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
ofx flow tools --all                          # Install workflow tool dependencies
ofx flow visualize recon.yml --format dot      # Render the DAG (DOT format)
ofx flow run recon.yml --output ./runs/recon  # Custom output directory
```

## What to read next

- [Workflows](../guide/workflows.md) — Workflow structure and features
- [Jobs & Steps](../guide/jobs-steps.md) — Step types and configuration
- [Templates](../guide/templates.md) — Jinja2 helpers and functions
- [Secrets & Inputs](../guide/secrets-inputs.md) — Credential management
- [Cloud Runners](../guide/cloud-runners.md) — Remote execution
