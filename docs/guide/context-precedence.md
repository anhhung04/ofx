# Context Precedence (Workflow / Job / Step)

OFX resolves execution context in layers. Each layer can add or override values.

## Precedence order

1) **Workflow** defaults and envs
2) **Job** envs / defaults
3) **Step** envs / working directory / run inputs
4) **Runtime updates** (template resolution, run_if evaluation)

## What merges vs replaces

- **envs**: merged, later layers override earlier keys
- **inputs**: merged, later layers override earlier keys
- **secrets**: merged, step secrets override job/workflow when provided
- **vars**: merged, later layers override earlier keys
- **working_directory**: step overrides job/workflow

## Example

```yaml
jobs:
  build:
    envs: { ENV: "job", PATH: "/job" }
    steps:
      - run: echo "hello"
        envs: { ENV: "step" }
```

Effective env:

```
ENV=step
PATH=/job
```

## Notes

- `run_if` is evaluated **after** template resolution for the step/job.
- For reusable workflows, `inputs` and `secrets` are mapped from the call site into the child context before execution.
