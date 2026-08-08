# OFX: Offensive Flow Executor

OFX is a workflow engine for red team operations — define attack chains as YAML, run jobs in parallel, execute remotely on cloud infrastructure, and keep outputs organized per engagement.

## Why OFX

- **Workflow-driven** — YAML-defined jobs with dependency-aware parallel scheduling.
- **Cross-platform** — runs on Linux, macOS, and Windows; supports arm64 and amd64.
- **Two step types** — `run:` for shell commands, `script:` for Python logic.
- **Jinja2 templating** — access `inputs`, `secrets`, `env`, `matrix`, and `ctx` in your workflows.
- **Cloud execution** — provision AWS/DigitalOcean instances and run workflows remotely.
- **Detached sessions** — long-running background jobs with status polling.

## Quick Example

```yaml
name: recon
jobs:
  scan:
    steps:
      - name: port-scan
        run: nmap -sV -sC {{ inputs.target }} -oA {{ env.OFX_RUN_DIR }}/nmap
      - name: web-probe
        run: httpx -l {{ env.OFX_RUN_DIR }}/nmap.xml -tech-detect -silent
```

```bash
ofx flow run recon.yml --input target=10.10.10.5
```

## Install

```bash
uv tool install ofx        # recommended
pip install ofx             # or pip
ofx --version               # verify
```

## Workflow Collections

OFX ships with **34 built-in workflows** organized by pentest phase:

| Collection | Workflows | Purpose |
|---|---|---|
| **recon/** | 4 | OSINT, subdomain enum, DNS, cloud discovery |
| **scan/** | 4 | Host discovery, port scan, web probe, SSL audit |
| **vuln/** | 5 | Nuclei, web app scan, secrets, SAST, containers |
| **exploit/** | 6 | AD attacks, credentials, hash cracking, C2, payloads |
| **post/** | 8 | Priv esc, lateral, credential dump, persistence, exfil, OPSEC |
| **utility/** | 3 | Target parsing, IOC extraction, results export |
| **setup/** | 4 | Cloud infra, Docker lab, Git guard, proxy config |

## Step Types

```yaml
steps:
  - name: cli-tool
    run: nmap -sV {{ inputs.target }}              # shell command

  - name: python-logic
    script: |
      import os, json
      data = json.load(open("results.json"))
      print(f"Found {len(data)} items")
```

## Start Here

- [Installation](getting-started/installation.md)
- [Quick Start](getting-started/quickstart.md)
- [Workflows Guide](guide/workflows.md)
- [Built-in Workflows](guide/builtin-workflows/recon.md)
- [CLI Commands](cli/commands.md)