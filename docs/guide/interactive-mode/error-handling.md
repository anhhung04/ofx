# Error Handling & Troubleshooting for Interactive Mode

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

---

## Troubleshooting

### Interactive Mode Not Working
**Problem:** Step doesn't accept input despite `interactive: true`

**Solution:** Check if the job is in a parallel stage:
```bash
# View execution stages
ofx flow run workflow.yml --debug
```
Look for log messages indicating parallel execution. If jobs run in parallel, add dependencies to make them sequential.

### Shell Exit Handling
**Problem:** Exiting the shell with `exit` or `Ctrl+D` causes an error in the workflow.

**Solution:** As of vX.Y.Z, OFX treats exit codes 0, 127, and 130 as clean exits in interactive mode. You can safely exit the shell and the workflow will continue. Only unexpected errors will stop the workflow.

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
