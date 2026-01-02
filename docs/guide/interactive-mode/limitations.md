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
name: Parallel Interactive Test
jobs:
  job1:
    name: Interactive Job
    steps:
      - name: Launch bash shell
        run: bash
        interactive: true  # Disabled if job2 runs in parallel
  job2:  # No 'needs' - runs in parallel with job1
    name: Parallel Job
    steps:
      - name: Print message
        run: echo "parallel"
```

**Solution:** Use job dependencies to ensure jobs run sequentially:

```yaml
name: Sequential Interactive Test
jobs:
  job1:
    name: Interactive Job
    steps:
      - name: Launch bash shell
        run: bash
        interactive: true  # ✓ Works
  job2:
    name: Follow-up Job
    needs: job1  # Runs after job1 completes
    steps:
      - name: Print message
        run: echo "sequential"
```
