# Interactive Mode Usage

Interactive mode passes stdin/stdout through directly so you can drive shells and tools.

## When It Works

- Only in single-job stages. If a stage has multiple jobs, `interactive: true` is ignored.
- Step must set `interactive: true`; `timeout` is in minutes.
- Reusable workflows (`uses`) are always non-interactive.

## Basic Usage

### Interactive Shell
```yaml
name: Interactive Shell Example
jobs:
  shell_session:
    steps:
      - name: Start Bash Shell
        run: bash
        interactive: true
        timeout: 10  # Optional timeout in minutes
```

### Interactive Python REPL
```yaml
name: Python REPL Example
jobs:
  python_session:
    steps:
      - name: Start Python REPL
        run: python3
        interactive: true
      - name: Continue After REPL
        run: echo "Session completed"
```

### Interactive Tool
```yaml
name: Run Interactive Tool
jobs:
  exploit_tool:
    steps:
      - name: Use Metasploit Console
        run: msfconsole
        interactive: true
        timeout: 30
```

## Tips for a Smooth Session

- Keep one interactive step per stage to guarantee pass-through.
- Set generous but finite `timeout` to avoid hung runs.
- Pre-install tools in a prior job/step to shorten the interactive window.
- Use `run_if: failure()` to drop into a shell only when something breaks.
