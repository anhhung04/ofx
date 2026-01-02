# Detection & Execution Modes

## Single-Job Stage Detection

The workflow runner automatically analyzes job dependencies and determines which jobs can run in parallel:

```yaml
name: Interactive Mode Detection
jobs:
  # Stage 1: job1 alone - interactive allowed
  job1:
    steps:
      - name: Interactive Step
        run: bash
        interactive: true  # ✓ Works - alone in stage
  # Stage 2: job2 and job3 in parallel - interactive disabled
  job2:
    needs: job1
    steps:
      - name: Try Interactive
        run: bash
        interactive: true  # ✗ Disabled - job3 runs in parallel
  job3:
    needs: job1
    steps:
      - name: Normal Step
        run: echo "parallel with job2"
  # Stage 3: job4 alone - interactive allowed again
  job4:
    needs: [job2, job3]
    steps:
      - name: Interactive Again
        run: python3
        interactive: true  # ✓ Works - alone in stage
```

## Execution Modes

**Interactive Mode (interactive: true):**
- stdin/stdout/stderr connected to terminal
- User can type input
- Output appears in real-time
- Perfect for shells, REPLs, debuggers

**Normal Mode (interactive: false or not specified):**
- Output captured and logged
- No stdin input possible
- Can run in parallel with other jobs
- Default behavior
