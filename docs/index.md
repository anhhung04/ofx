# OFX: Offensive Flow Executor

OFX is an async-first workflow engine for red-team automation.

It lets you define operations as YAML workflows, run jobs in parallel, wrap 90+ security tools with structured output parsing, execute remotely on cloud infrastructure, and keep outputs organized per run.

## Why OFX

- **Workflow-driven execution** with dependency-aware parallel scheduling.
- **90+ built-in task wrappers** — nmap, nuclei, httpx, subfinder, and more — with structured typed outputs.
- **Reusable templates** with Jinja context (`inputs`, `secrets`, `matrix`, `ctx`).
- **Cloud and fleet execution** with profile-based provisioning.
- **Detached sessions** for long-running jobs.

## Quick Example

```yaml
name: recon
jobs:
  scan:
    steps:
      - task: nmap
        name: port-scan
        with:
          target: "{{ inputs.target }}"
          ports: "80,443,8080"
      - task: nuclei
        with:
          target: "{{ inputs.target }}"
          severity: "critical,high"
```

```bash
ofx flow run recon.yml --input target=10.10.10.5
```

Or run a single task directly — no YAML needed:

```bash
ofx flow tasks run nmap 10.10.10.5 --opt ports=1-1000
```

## Install

```bash
# uv (recommended)
uv tool install ofx

# or pip
pip install ofx

# verify
ofx --version
```

## Start Here

- [Installation](getting-started/installation.md)
- [Quick Start](getting-started/quickstart.md)
- [Tasks Guide](guide/tasks.md) — 90+ built-in security tools
- [Workflows Guide](guide/workflows.md)
- [CLI Commands](cli/commands.md)
- [API Overview](api/overview.md)

## Typical Workflow Lifecycle

1. Define workflow YAML (`jobs`, `steps`, `task`, `inputs`, `secrets`).
2. Validate schema and structure (`ofx flow validate`).
3. Execute locally or on cloud runners.
4. Inspect logs/artifacts in the run output path.
5. Reuse/compose workflows via collections.

## Next Steps

If you are new, continue with the [Quick Start](getting-started/quickstart.md).

If you already run workflows, jump to [Advanced topics](advanced/llm-agent-guide.md) and [Performance](advanced/performance.md).
