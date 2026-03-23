# OFX: Offensive Flow Executor

OFX is an async-first workflow engine for red-team automation.

It lets you define operations as YAML workflows, run jobs in parallel, use built-in APIs, execute remotely on cloud infrastructure, and keep outputs organized per run.

## Why OFX

- **Workflow-driven execution** with dependency-aware scheduling.
- **Reusable templates** with Jinja context (`inputs`, `secrets`, `matrix`, `ctx`).
- **Built-in task wrappers** with structured outputs.
- **Cloud and fleet execution** with profile-based provisioning.
- **Detached sessions** for long-running jobs.

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
- [Workflows Guide](guide/workflows.md)
- [CLI Commands](cli/commands.md)
- [API Overview](api/overview.md)

## Typical Workflow Lifecycle

1. Define workflow YAML (`jobs`, `steps`, `inputs`, `secrets`).
2. Validate schema and structure.
3. Execute locally or on cloud runners.
4. Inspect logs/artifacts in the run output path.
5. Reuse/compose workflows via collections.

## Next Steps

If you are new, continue with the [Quick Start](getting-started/quickstart.md).

If you already run workflows, jump to [Advanced topics](advanced/llm-agent-guide.md) and [Performance](advanced/performance.md).
