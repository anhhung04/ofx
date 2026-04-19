# Workflow Dependencies

Dependencies control the execution order of jobs in an OFX workflow. Use the `needs` field to specify which jobs must complete before a job can start.

---

## Syntax
```yaml
name: Build Pipeline
jobs:
  build:
    name: Build Application
    steps:
      - name: Compile code
        run: make
  test:
    name: Run Tests
    needs: build
    steps:
      - name: Execute tests
        run: pytest
  deploy:
    name: Deploy Application
    needs: [test]
    steps:
      - name: Deploy to production
        run: ./deploy.sh
```

---

## How It Works
- Jobs without `needs` run in the first stage (in parallel)
- Jobs with `needs` wait for all listed dependencies to complete
- You can specify a single job (`needs: build`) or a list (`needs: [build, test]`)
- Dependencies are topologically sorted into parallel stages — see [Stages](stages.md)

---

## Conditional Execution

Use `if` (alias: `run_if`) to control whether a job runs based on the outcome of its dependencies:

```yaml
jobs:
  scan:
    steps:
      - run: nmap {{ inputs.target }}

  exploit:
    needs: [scan]
    if: success()              # Only run if scan succeeded (default behavior)
    steps:
      - run: python exploit.py

  cleanup:
    needs: [exploit]
    if: always()               # Run regardless of exploit outcome
    steps:
      - run: ./cleanup.sh

  notify-failure:
    needs: [exploit]
    if: failure()              # Only run if exploit failed
    steps:
      - run: echo "Exploit failed" | notify
```

**Available conditions:**

| Condition | Behavior |
|-----------|----------|
| `success()` | Run only if all dependencies succeeded (default) |
| `failure()` | Run only if any dependency failed |
| `always()` | Run regardless of dependency outcomes |
| `true` / `false` | Unconditional enable/disable |
| Jinja2 expression | Evaluated at runtime (e.g. `"{{ inputs.mode == 'full' }}"`) |

---

## Example: Multiple Dependencies
```yaml
name: Complex Attack Chain
jobs:
  setup:
    name: Environment Setup
    steps:
      - name: Initialize environment
        run: ./setup.sh
  scan:
    name: Port Scan
    needs: setup
    steps:
      - name: Scan target
        run: nmap {{ inputs.target }}
  exploit:
    name: Exploitation
    needs: [setup, scan]
    steps:
      - name: Run exploit
        run: python exploit.py
```

In this example, `exploit` waits for both `setup` and `scan` to complete before running.

---

## Validation

OFX validates dependencies at parse time:

- All job IDs referenced in `needs` must exist in the workflow
- Circular dependencies are detected and rejected
- Use `ofx flow validate workflow.yml` to check before running

---

## Best Practices
- Use dependencies to enforce correct execution order and avoid race conditions
- Use `if: always()` for cleanup jobs that must run regardless of failures
- Use `if: failure()` for notification or rollback jobs
- Keep dependency chains shallow — deeply nested chains reduce parallelism

---

## See Also
- [Workflow Stages](stages.md)
- [Workflow Examples](examples.md)