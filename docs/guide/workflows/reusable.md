# Reusable Workflows (`uses:`)

OFX lets you reference another workflow file via the `uses:` key. The lookup follows the same rules as `ofx flow run`:

- Local relative/absolute path
- Workflow name in `$HOME/.ofx/workflows`
- Remote HTTP/HTTPS URL
- Git repository URL (e.g. `https://github.com/user/repo`)

```yaml
jobs:
  sub:
    uses: ./shared/credential-check.yml
    with:
      target: {{ inputs.target }}
```

The referenced file is parsed into a `Workflow` object (`src/ofx/models/workflow.py`) and executed in the current run context. Secrets/inputs can be passed via `with:` just like a function call.

> **Note:** When a remote workflow is used, OFX caches the file under `$HOME/.ofx/cache` and validates its integrity on each run.
