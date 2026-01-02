# Limitations of Interactive Mode

## Cannot Use With Workflows

Interactive mode does not work with nested workflows:

```yaml
jobs:
  nested:
    steps:
      - name: Won't Work
        uses: ./other-workflow.yml
        interactive: true  # ⚠️ Warning: ignored for workflow steps
```

## Parallel Jobs Disable Interactive

If multiple jobs run in the same stage, interactive mode is automatically disabled:

```yaml
jobs:
  job1:
    steps:
      - run: bash
        interactive: true  # Disabled if job2 runs in parallel
  job2:  # No 'needs' - runs in parallel with job1
    steps:
      - run: echo "parallel"
```

**Solution:** Use job dependencies to ensure jobs run sequentially:

```yaml
jobs:
  job1:
    steps:
      - run: bash
        interactive: true  # ✓ Works
  job2:
    needs: job1  # Runs after job1 completes
    steps:
      - run: echo "sequential"
```
