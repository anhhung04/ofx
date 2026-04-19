# Context Precedence (Workflow / Job / Step)

OFX resolves execution context in layers. Each layer can add or override values from the previous one.

## Precedence order

1) **Workflow** defaults and env
2) **Job** env / defaults
3) **Step** env / working directory / run inputs
4) **Runtime** — template resolution, `if` condition evaluation

## What merges vs replaces

| Context | Behavior |
|---------|----------|
| `env` | Merged — later layers override matching keys |
| `inputs` | Merged — later layers override matching keys |
| `secrets` | Merged — step secrets override job/workflow when provided |
| `vars` | Merged — later layers override matching keys |
| `working-directory` | Replaced — step overrides job, job overrides workflow |

## Example

```yaml
env:
  GLOBAL: "workflow"

jobs:
  build:
    env:
      ENV: "job"
      PATH: "/job"
    steps:
      - run: echo "$ENV $PATH $GLOBAL"
        env:
          ENV: "step"
```

Effective env for the step:

```
ENV=step          # step overrides job
PATH=/job         # inherited from job
GLOBAL=workflow   # inherited from workflow
```

## Notes

- `if` conditions are evaluated **after** template resolution for the step/job.
- For reusable workflows, `inputs` and `secrets` are mapped from the call site into the child context before execution.
- Profile settings (rate limits, proxy, etc.) are injected into the workflow context before jobs start.

## Auto-injected environment variables

These variables are set automatically by OFX and available in all steps:

| Variable | Description |
|---|---|
| `OFX_OUTPUTS` | Path to the step outputs file (write `key=value` lines) |
| `OFX_RUN_DIR` | Per-run unique temp directory (cleaned up after workflow) |
| `OFX_RATE_LIMIT` | Profile rate limit (when a profile is active) |
| `OFX_THREADS` | Profile thread count |
| `OFX_PROXY` | Profile proxy URL |
| `OFX_USER_AGENT` | Profile User-Agent string |

## See also

- [Built-in Variables & Functions](context-variables-functions.md)
- [Secrets & Inputs](secrets-inputs.md)
- [Profiles](profiles.md)
