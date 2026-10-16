
# Practical Examples for Interactive Mode

This page demonstrates a wide range of real-world use cases for OFX interactive mode, with detailed YAML and commentary. Use these as templates for your own workflows.

---

## 1. Exploit Development & Debugging

Run GDB interactively, then save findings:
```yaml
name: Exploit Debugging
jobs:
  setup:
    steps:
      - name: Prepare Environment
        module: shell
        with:
          cmd: |
            mkdir -p /tmp/exploit
            cp ./vuln ./vuln.bak
  debug:
    needs: setup
    steps:
      - name: GDB Session
        module: shell
        with:
          cmd: gdb ./vuln
        interactive: true
        timeout: 30
        working_directory: /tmp/exploit
      - name: Save GDB Log
        module: shell
        with:
          cmd: cp gdb.txt /tmp/exploit/gdb.log
```
**Why:** Use for binary analysis, exploit dev, or live debugging. All stdin/stdout is passed through.

---

## 2. Database Shells & Data Export

Connect to a database interactively, then export data:
```yaml
name: Database Session
jobs:
  db:
    steps:
      - name: MySQL Shell
        module: shell
        with:
          cmd: mysql -h {{ inputs.db_host }} -u {{ inputs.db_user }} -p{{ secrets.db_pass }}
        interactive: true
        timeout: 15
      - name: Export Data
        module: shell
        with:
          cmd: mysqldump {{ inputs.db_name }} > dump.sql
```
**Why:** Use for manual queries, schema inspection, or troubleshooting.

---

## 3. Network Tools (Netcat, SSH, Telnet)

Interact with remote services or open shells:
```yaml
name: Netcat Example
jobs:
  netcat:
    steps:
      - name: Open Netcat
        module: shell
        with:
          cmd: nc {{ inputs.target_ip }} {{ inputs.target_port }}
        interactive: true
        timeout: 10
      - name: Log
        module: shell
        with:
          cmd: echo "Netcat session done"
```

SSH interactive session:
```yaml
name: SSH Session
jobs:
  ssh:
    steps:
      - name: SSH Login
        module: shell
        with:
          cmd: ssh user@{{ inputs.host }}
        interactive: true
        timeout: 20
```

---

## 4. Python & IPython REPLs

Launch a Python shell for live testing:
```yaml
name: Python REPL
jobs:
  py:
    steps:
      - name: Start Python
        module: shell
        with:
          cmd: python3 -i
        interactive: true
      - name: Save Output
        module: shell
        with:
          cmd: cp ~/.python_history python_history.txt
```

Or use IPython for advanced features:
```yaml
name: IPython Session
jobs:
  ipy:
    steps:
      - name: IPython
        module: shell
        with:
          cmd: ipython3
        interactive: true
        env:
          PYTHONPATH: /opt/custom
      - name: Save History
        module: shell
        with:
          cmd: cp ~/.ipython/profile_default/history.sqlite ipython_history.db
```

---

## 5. Metasploit & Custom Tools

Metasploit console:
```yaml
name: Metasploit
jobs:
  msf:
    steps:
      - name: Start msfconsole
        module: shell
        with:
          cmd: msfconsole
        interactive: true
        timeout: 30
```

Custom CLI tool:
```yaml
name: Custom Tool
jobs:
  tool:
    steps:
      - name: Run Custom CLI
        module: shell
        with:
          cmd: ./my_interactive_tool --shell
        interactive: true
```

---

## 6. Error Handling & Exit Codes

Interactive steps handle exits gracefully:
```yaml
jobs:
  shell:
    steps:
      - name: Bash
        module: shell
        with:
          cmd: bash
        interactive: true
        timeout: 10
      - name: After Shell
        module: shell
        with:
          cmd: echo "Shell exited"
```
*Exiting with `exit`, `Ctrl+D`, or `Ctrl+C` is treated as a clean exit. Nonzero exit codes (except 127/130) stop the job unless `continue-on-error: true` is set.*

---

## 7. Advanced: Conditional Interactive Steps

Run an interactive shell only if a previous step fails:
```yaml
jobs:
  test:
    steps:
      - name: Run Tests
        module: shell
        with:
          cmd: pytest
      - name: Debug Shell
        module: shell
        with:
          cmd: bash
        interactive: true
        if: failure()
```

---

## 8. Best Practices

- Always set a `timeout` to avoid hanging sessions.
- Use job dependencies (`needs:`) to ensure only one interactive job runs at a time.
- Use `env:` to set environment variables for your session.
- Use `if:` for conditional debugging.
- Save session logs or history for later review.

---

## 9. Troubleshooting

- If interactive mode doesn't work, check for parallel jobs in the same stage.
- Use `ofx flow run workflow.yml --debug` to inspect execution stages.
- Some tools require special flags for interactive mode (e.g., `python3 -i`).

---

For more, see the [Usage](usage.md), [Detection & Execution](detection.md), and [Error Handling](error-handling.md) pages.
