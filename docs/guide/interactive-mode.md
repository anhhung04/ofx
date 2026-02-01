# Interactive Mode

Interactive steps wire stdin/stdout/stderr to your terminal. They only work when the job runs alone in its stage.

## Quick rules

- `interactive: true` allowed only if the stage has a single job; parallel stages disable it automatically.
- Ignored for `uses:` (nested workflows cannot be interactive).
- Exit codes 0, 127, 130 are treated as clean exits; others fail unless `continue_on_error`.

## Minimal example

```yaml
jobs:
  shell:
    steps:
      - run: bash
        interactive: true   # works (single-job stage)
        timeout: 15
```

## Make a stage serial

```yaml
jobs:
  prepare:
    steps: [{ run: ./prepare.sh }]
  session:
    needs: prepare
    steps:
      - run: mysql -h {{ inputs.db_host }} -u {{ inputs.db_user }} -p{{ secrets.db_pass }}
        interactive: true
```

## Troubleshooting

- Not interactive? Check if another job runs in the same stage; add `needs` to serialize.
- Nested workflow? `interactive` is ignored on `uses:` steps.
- Hanging? Set a `timeout`.

See the subpages for details: [usage](interactive-mode/usage.md), [detection](interactive-mode/detection.md), [limitations](interactive-mode/limitations.md), [examples](interactive-mode/examples.md), [best practices](interactive-mode/best-practices.md), [error handling](interactive-mode/error-handling.md).
