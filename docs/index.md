# Welcome to OFX

Build and run red-team workflows with async execution, reusable subflows, hooks, and tool installers. Use this page as a launchpad to the rest of the docs.

## Before You Start

- Install: `uv sync` (or `pip install .`), Python 3.14+, `git`
- Check: `ofx --help` and `ofx doctor`
- Docs locally: `ofx docs serve`

## Quick Commands

- Validate: `ofx flow validate <workflow>`
- Run: `ofx flow run <workflow> --input key=val --secret NAME=val`
- Secrets: `ofx secret set NAME`
- Explore: `ofx x run <workflow>` (alias)

## Minimal Workflow (runnable)

```yaml
name: hello
jobs:
  greet:
    steps:
      - run: echo "Hello from OFX"
```

Save as `hello.yml` and run:

```bash
ofx flow run hello
```

Expected output: progress spinner plus a single `Hello from OFX` line.

## Where to Go Next

- Start: [quickstart](getting-started/quickstart.md), [concepts](getting-started/concepts.md)
- Build: [workflows](guide/workflows.md), [jobs & steps](guide/jobs-steps.md), [templates](guide/templates.md)
- Operate: [secrets & inputs](guide/secrets-inputs.md), [interactive mode](guide/interactive-mode.md)
- Reference: [commands](cli/commands.md), [API overview](api/overview.md)
