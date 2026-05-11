# Workflows

This page covers the workflow model, execution behavior, and best practices.

## Minimal workflow

```yaml
name: demo

jobs:
  run:
    steps:
      - run: echo "hello"
```

## Core structure

```yaml
name: recon-pipeline
description: Example workflow

dispatch:
  inputs:
    target:
      type: string
      required: true

call:
  secrets:
    API_KEY:
      required: false

env:
  LOG_LEVEL: info

defaults:
  shell: bash

jobs:
  recon:
    steps:
      - run: subfinder -d {{ inputs.target }} -o {{ ctx.output_path }}/subs.txt

  scan:
    needs: [recon]
    steps:
      - run: naabu -list {{ ctx.output_path }}/subs.txt -o {{ ctx.output_path }}/ports.txt
```

## Required and optional fields

- Required:
  - `name`
  - `jobs`
- Common optional fields:
  - `description`, `tags`
  - `dispatch.inputs`
  - `call.secrets`
  - `env`, `defaults`, `tools`

## Execution model

- Jobs without `needs` run in parallel.
- `needs` creates dependency edges.
- Steps run sequentially within each job.
- A step must define exactly one execution mode:
  - `run`
  - `script`
  - `script_file`
  - `uses`
  - `task`
  - `pipe`

## Matrix strategy

Use `strategy.matrix` for combinational job expansion:

```yaml
jobs:
  scan:
    strategy:
      matrix:
        port: [80, 443, 8080]
      max_parallel: 2
    steps:
      - run: nmap -p {{ matrix.port }} {{ inputs.target }}
```

## Workflow sources

You can run workflows from:

- Local file paths.
- Names resolved in workflow search paths.
- HTTP/HTTPS URLs.
- Git repositories.

## Reusable workflows

Use `uses` in a step to call another workflow:

```yaml
steps:
  - uses: workflows/recon.yml
    with:
      target: "{{ inputs.target }}"
```

## Outputs and artifacts

Always write artifacts under `{{ ctx.output_path }}`.

```yaml
- run: nmap -oN {{ ctx.output_path }}/nmap.txt {{ inputs.target }}
```

## Durable execution

You can enable resume behavior with durable checkpoints:

```yaml
defaults:
  durable:
    enabled: true
    resume: true
    backend: file
```

## Validation and run

```bash
ofx flow validate recon-pipeline.yml
ofx flow run recon-pipeline.yml --input target=example.com
```

## Best practices

- Keep jobs focused and composable.
- Validate early (`flow validate`) before execution.
- Use clear job IDs and step names.
- Prefer `ctx.output_path` over hardcoded paths.
- Keep secrets in `ofx secret`, not inline YAML.

## See also

- [Workflow structure details](workflows/structure.md)
- [Dependencies](workflows/dependencies.md)
- [Reusable workflows](workflows/reusable.md)
- [Jobs & Steps](jobs-steps.md)
