# Interactive Mode Usage

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
