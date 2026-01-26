# Outputs

Outputs let steps and jobs share data so you can chain results and build dynamic workflows.

---

## What gets captured automatically
- `step.stdout` — full command output as a string
- `step.stdout_lines` — output split into a list of lines

Use these in templates without any extra configuration.

---

## Declaring step outputs
Expose specific values from a step by mapping them to templates:
```yaml
steps:
  - name: Scan
    run: nmap {{ inputs.target }}
    outputs:
      open_ports: "{{ step.stdout_lines }}"
```

Use them later in the same job:
```yaml
run: echo "Ports: {{ steps.0.outputs.open_ports }}"
```

---

## Job outputs
Promote step outputs to the job level so other jobs can consume them:
```yaml
jobs:
  scan:
    steps:
      - run: ...
        outputs:
          result: "{{ step.stdout }}"
    outputs:
      scan_result: "{{ steps.0.outputs.result }}"
```

Reference job outputs from dependents:
```yaml
run: echo "Scan: {{ jobs.scan.outputs.scan_result }}"
```

---

## Dynamic outputs with `OFX_OUTPUTS`
For commands that discover values at runtime, write key/value pairs to the temp file exposed via the `OFX_OUTPUTS` environment variable.

How it works for each command step:
1. OFX creates a temp file and sets `OFX_OUTPUTS` to its path.
2. Your command writes `key=value` lines to that file.
3. After the command finishes, OFX parses the file into `step.outputs`.
4. The temp file is removed automatically.

### Quick example
```yaml
jobs:
  discover:
    outputs:
      target_ip: "{{ steps.0.outputs.target_ip }}"
    steps:
      - name: Find target
        run: |
          target=$(dig +short example.com | head -1)
          echo "target_ip=$target" >> $OFX_OUTPUTS

  exploit:
    needs: [discover]
    steps:
      - run: echo "Attacking {{ jobs.discover.outputs.target_ip }}"
```

### Rules and limits
- One `key=value` per line; first `=` is the delimiter.
- Values are strings; the last write for a key wins.
- Available only in non-interactive steps; not set in interactive mode.
- Each step gets its own isolated temp file that is cleaned up automatically.

---

## Tips
- Prefer clear, stable output names so templates stay readable.
- Use `stdout_lines` for simple lists; use `OFX_OUTPUTS` when you need structured key/value results.

---

## See also
- [Steps](steps.md)
- [Jobs](jobs.md)
