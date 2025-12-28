jobs:
jobs:
jobs:

# Interactive Mode Documentation

This documentation has been split into multiple focused modules for easier searching and referencing:

- [Overview](interactive-mode/index.md)
- [Usage](interactive-mode/usage.md)
- [Detection & Execution](interactive-mode/detection.md)
- [Limitations](interactive-mode/limitations.md)
- [Examples](interactive-mode/examples.md)
- [Best Practices](interactive-mode/best-practices.md)
- [Error Handling & Troubleshooting](interactive-mode/error-handling.md)

Please see the above pages for details, YAML examples, and troubleshooting tips.

### Single-Job Stage Detection

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

### Execution Modes

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

## Limitations

### Cannot Use With Workflows

Interactive mode does not work with nested workflows:

```yaml
jobs:
  nested:
    steps:
      - name: Won't Work
        uses: ./other-workflow.yml
        interactive: true  # ⚠️ Warning: ignored for workflow steps
```

### Parallel Jobs Disable Interactive

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

## Practical Examples

### Exploit Development Workflow

```yaml
name: Interactive Exploit Development

jobs:
  setup:
    steps:
      - name: Prepare Environment
        run: |
          mkdir -p /tmp/exploit
          cd /tmp/exploit
  
  exploit:
    needs: setup
    steps:
      - name: GDB Session
        run: gdb ./vulnerable_binary
        interactive: true
        timeout: 30
        working_directory: /tmp/exploit
      
      - name: Save Findings
        run: |
          echo "GDB session completed" > session.log
        working_directory: /tmp/exploit
```

### Database Testing

```yaml
name: Database Interactive Session

jobs:
  db_session:
    steps:
      - name: Connect to MySQL
        run: mysql -h {{ inputs.db_host }} -u {{ inputs.db_user }} -p{{ secrets.db_pass }}
        interactive: true
        timeout: 15
      
      - name: Export Results
        run: mysqldump {{ inputs.db_name }} > dump.sql
```

### Network Tool Interaction

```yaml
name: Netcat Session

jobs:
  netcat:
    steps:
      - name: Interactive Netcat
        run: nc {{ inputs.target_ip }} {{ inputs.target_port }}
        interactive: true
        timeout: 10
      
      - name: Log Connection
        run: echo "Connection to {{ inputs.target_ip }}:{{ inputs.target_port }} completed"
```

### Python Script Development

```yaml
name: Interactive Python Testing

jobs:
  test_script:
    steps:
      - name: Run IPython
        run: ipython3
        interactive: true
        env:
          PYTHONPATH: /path/to/modules
      
      - name: Save Session History
        run: cp ~/.ipython/profile_default/history.sqlite ipython_history.db
```

## Best Practices

### Set Appropriate Timeouts

Always set timeouts for interactive sessions to prevent hanging:

```yaml
- name: Interactive Session
  run: bash
  interactive: true
  timeout: 15  # 15 minutes timeout
```

### Use for Debugging

Interactive mode is perfect for debugging workflow issues:

```yaml
jobs:
  debug:
    steps:
      - name: Run Commands
        run: |
          ./setup.sh
          ./process.sh
      
      - name: Debug Session
        run: bash
        interactive: true
        run_if: failure()  # Only run if previous step failed
```

### Combine with Hooks

Use hooks to prepare the environment before interactive sessions:

```yaml
jobs:
  interactive_session:
    hooks:
      on_start:
        run: echo "Starting interactive session..."
        language: shell
    
    steps:
      - name: Interactive Tool
        run: ./custom_tool
        interactive: true
```

### Sequential Dependencies

Ensure interactive jobs run sequentially:

```yaml
jobs:
  prepare:
    steps:
      - run: ./prepare.sh
  
  interact:
    needs: prepare  # Sequential execution
    steps:
      - run: bash
        interactive: true
  
  cleanup:
    needs: interact  # Runs after interaction
    steps:
      - run: ./cleanup.sh
```

## Error Handling & Exit Codes

OFX handles interactive shell exits gracefully:

- **Exit (exit/quit/close shell):** Exiting the shell (typing `exit`, `Ctrl+D`, or closing the terminal) is treated as a clean exit. The workflow continues to the next step or job.
- **Ctrl+C (SIGINT):** Pressing `Ctrl+C` in an interactive session (exit code 130) is also treated as a clean exit.
- **Command Not Found (127):** If you type a command that does not exist, the shell will show an error, but exiting the shell itself is not an error.
- **Other Errors:** Any other nonzero exit code is treated as a failure and will stop the job unless `continue_on_error: true` is set.

### Example: Handling Shell Exit

```yaml
jobs:
  interactive_shell:
    steps:
      - name: Start Interactive Bash
        run: bash
        interactive: true
        timeout: 10
      - name: After Shell
        run: echo "Shell session ended cleanly!"
```

If you type `exit` or press `Ctrl+D` in the shell, the workflow will continue to the next step. If you run an invalid command, you'll see an error, but you can still exit cleanly.

## Troubleshooting

### Interactive Mode Not Working

**Problem:** Step doesn't accept input despite `interactive: true`

**Solution:** Check if the job is in a parallel stage:
```bash
# View execution stages
ofx flow run workflow.yml --debug
```

Look for log messages indicating parallel execution. If jobs run in parallel, add dependencies to make them sequential.

### Timeout Issues

**Problem:** Interactive session terminates unexpectedly

**Solution:** Increase timeout:
```yaml
- name: Long Session
  run: tool
  interactive: true
  timeout: 60  # Increase from default
```

### Output Not Showing

**Problem:** Can't see output from interactive command

**Solution:** Ensure the command itself supports interactive mode. Some tools need flags:
```yaml
- name: Python Interactive
  run: python3 -i  # -i flag for interactive
  interactive: true
```

### Shell Exit Handling

**Problem:** Exiting the shell with `exit` or `Ctrl+D` causes an error in the workflow.

**Solution:** As of vX.Y.Z, OFX treats exit codes 0, 127, and 130 as clean exits in interactive mode. You can safely exit the shell and the workflow will continue. Only unexpected errors will stop the workflow.

## See Also

- [Workflows Guide](workflows.md) - Understanding job dependencies
- [Jobs & Steps](jobs-steps.md) - Job execution model
- [Hooks System](hooks.md) - Pre/post execution hooks
