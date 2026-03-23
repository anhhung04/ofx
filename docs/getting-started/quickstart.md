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

## 3) Create a workflow

Create `hello.yml`:

```yaml
name: hello-world

dispatch:
  inputs:
    target:
      type: string
      required: true
      description: Target label to print

jobs:
  greet:
    steps:
      - run: echo "Hello {{ inputs.target }} from OFX"

  metadata:
    needs: [greet]
    steps:
      - run: echo "Run ID: {{ ctx.run_id }}"
      - run: echo "Output: {{ ctx.output_path }}"
```

## 4) Validate and run

```bash
ofx flow validate hello.yml
ofx flow run hello.yml --input target=team
```

## 5) Add secrets (optional)

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

## 6) Useful next commands

```bash
ofx flow visualize hello.yml --format mermaid
ofx flow run hello.yml --output ./runs/hello
ofx doctor fleet
```

## What to read next

- [Workflows](../guide/workflows.md)
- [Jobs & Steps](../guide/jobs-steps.md)
- [Templates](../guide/templates.md)
- [Secrets & Inputs](../guide/secrets-inputs.md)
- [Cloud Runners](../guide/cloud-runners.md)
