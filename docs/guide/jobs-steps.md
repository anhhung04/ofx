# Jobs & Steps

> [!INFO]
> Jobs run in parallel (unless dependent), steps run sequentially within a job.

---

## Jobs Overview

Jobs are the main execution units in a workflow:

```yaml
jobs:
  scan:
    needs: []                  # Dependencies (empty = parallel)
    run_if: success()          # Conditional (alias: if)
    env:
      LOG_LEVEL: INFO          # Job-wide environment
    steps:
      - module: shell
        with:
          cmd: nmap {{ inputs.target }}
```

| Property         | Type      | Description                                      |
|------------------|-----------|--------------------------------------------------|
| `name`           | str       | Job display name                                 |
| `steps`          | list      | **Required.** Steps to execute                   |
| `needs`          | list/str  | Job dependencies (for ordering)                  |
| `if`             | bool/str  | Conditional execution (alias: `run_if`)          |
| `strategy`       | object    | Matrix strategy config                           |
| `env`            | dict      | Environment variables for all steps              |
| `outputs`        | dict      | Job outputs (template-resolved)                  |
| `defaults`       | object    | Default run config overrides                     |
| `cloud`          | str/object| Cloud VPS config — profile name or `CloudConfig` |

> [!TIP]
> See the [Jobs Overview](#jobs-overview) above for all available options.

---

## Steps Overview

Each step executes exactly **one** action:

| Action | Description |
|--------|-------------|
| `module: shell` | Shell command (`with.cmd`) |
| `module: python` | Inline Python (`with.script`) or Python file (`with.script_file`) |
| `module: <file>::<func>` | User-defined function module (defaults to `run`) |
| `uses` | Reusable workflow reference |
| `pipe` | Declarative ETL pipeline (see [Pipe Steps](jobs-steps/steps.md#pipe-steps)) |


### Step Properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `name` | str | - | Descriptive name |
| `module` / `uses` / `pipe` | str/dict | - | **Required.** Exactly one action |
| `timeout` | int/str | 1440 | Max duration in minutes (supports Jinja2 expressions) |
| `retry` | int | 0 | Retry attempts on failure |
| `retry-delay` | int | 5 | Seconds between retries |
| `continue-on-error` | bool | false | Continue on failure |
| `if` | bool\|str | true | Conditional execution (`success()`/`failure()`/`canceled()`/`always()`) |
| `env` | dict | {} | Step environment variables |
| `shell` | str | /bin/bash | Shell used by `module: shell` steps |
| `working-directory` | str | cwd | Execution directory |
| `log-stdout` | bool\|str | false | Save full stdout to `stdout_<job>_<step>.log` |
| `log-command` | bool\|str | false | Log the resolved command/script |
| `interactive` | bool | false | Interactive mode (single-job stages only) |
| `with` | dict | {} | Module arguments / inputs for `uses` |
| `secrets` | dict\|"inherit" | {} | Secrets for `uses` |
| `store-creds` | bool | null | Auto-store `user_account` credentials from module outputs |

---

## 🖥️ Shell Modules (`module: shell`)

```yaml
steps:
  - name: Port scan
    module: shell
    with:
      cmd: nmap -p {{ inputs.ports }} {{ inputs.target }}
    timeout: 30
    retry: 1
    retry-delay: 5
    env:
      MODE: fast
    working-directory: ./scans
```

### Multi-line Commands
```yaml
- name: Complex scan
  module: shell
  with:
    cmd: |
      echo "Starting scan..."
      nmap -sS {{ inputs.target }} -oX scan.xml
      mv scan.xml {{ ctx.output_path }}/
```

---

## 🐍 Python Modules (`module: python`)

```yaml
steps:
  - name: Process data
    module: python
    with:
      script: |
        import json

        data = {"target": "{{ inputs.target }}"}
        with open("{{ ctx.output_path }}/data.json", "w") as f:
          json.dump(data, f)
```

### Python Script Files (`with.script_file`)

Execute an external Python script file. Paths are resolved relative to the workflow directory unless absolute.

```yaml
steps:
  - name: Run complex analysis
    module: python
    with:
      script_file: scripts/analyze_results.py
    env:
      THRESHOLD: "0.95"
```

### Inter-Step Communication
```yaml
- name: Publish status
  module: python
  with:
    script: |
      publish('status', {'state': 'running', 'progress': 50})

- name: Wait for config
  module: python
  with:
    script: |
      config = wait_for('config', lambda d: d.get('ready'))
      print(f"Got config: {config}")
```

---

## 🔧 User-defined Modules (`module: <file>::<func>`)

Point `module:` at your own Python file (optionally with `::func`, default `run`) to run custom logic — scanners, exploit attempts, parsers. The function receives `ctx` with `ctx.inputs` (the `with:` arguments), `ctx.secrets`, `ctx.env`, `ctx.working_directory`, `ctx.add_outputs(**kwargs)`, and `ctx.log(msg)`, and may return a dict merged into the step outputs:

```yaml
steps:
  - module: modules/port_scan.py
    name: port-scan
    with:
      target: "{{ inputs.target }}"
      ports: "80,443,8080"

  - module: modules/vuln_scan.py
    name: vuln-scan
    with:
      target: "{{ inputs.target }}"
```

Modules that emit `typed_outputs` (Port, Url, Vulnerability, etc.) via `add_outputs(typed_outputs=[...])` can be chained with template helpers:

```yaml
- module: shell
  with:
    cmd: |
      echo "Open ports: {{ ports(steps['port-scan'].outputs.typed_outputs) | length }}"
      echo "Vulns found: {{ vulns(steps['vuln-scan'].outputs.typed_outputs) | length }}"
```

See [Steps → Modules](jobs-steps/steps.md#modules) for the full module contract and path resolution rules.

---

## 🔄 Pipe Steps (`pipe`)

Pipe steps provide declarative ETL (Extract-Transform-Load) pipelines for transforming data between steps without writing scripts.

```yaml
steps:
  - module: modules/port_scan.py
    name: scan
    with:
      target: "{{ inputs.target }}"

  - name: filter-results
    pipe:
      input: "{{ steps['scan'].outputs.typed_outputs }}"
      filter: "port > 1024"
      sort: port
      unique: host
      format: csv
      field: host,port
```

Pipe steps support: `input`, `filter`, `map`, `flatten`, `sort`, `reverse`, `unique`, `group_by`, `offset`, `limit`, `format`, `field`, `separator`, and `headers`.

Results are accessible via `{{ steps['filter-results'].outputs.stdout }}` and `{{ steps['filter-results'].outputs.file }}`.

See the [Pipe Steps reference](jobs-steps/steps.md#pipe-steps) for full configuration details and ETL helper functions.

---

## 📁 Working with Outputs

### Save to Output Directory
```yaml
- name: Save scan results
  module: shell
  with:
    cmd: nmap {{ inputs.target }} > {{ ctx.output_path }}/scan.txt
```

### Share Data Between Steps
```yaml
steps:
  - name: Generate data
    module: python
    with:
      script: |
        import json
        data = {"ports": [80, 443, 8080]}
        with open("{{ ctx.output_path }}/data.json", "w") as f:
          json.dump(data, f)

  - name: Use data
    module: python
    with:
      script: |
        import json
        with open("{{ ctx.output_path }}/data.json") as f:
          data = json.load(f)
        print(f"Ports: {data['ports']}")
```

### Output Variables with OFX_OUTPUTS
```yaml
- name: Export variables
  module: shell
  with:
    cmd: |
      echo "PORT=8080" >> $OFX_OUTPUTS
      echo "STATUS=ready" >> $OFX_OUTPUTS
```

---

## ⚠️ Error Handling

### Exit Codes
```yaml
- name: Check service
  module: python
  with:
    script: |
      import sys
      import socket

      try:
          s = socket.socket()
          s.connect(("{{ inputs.target }}", 80))
          print("Service is up")
          sys.exit(0)
      except:
          print("Service is down")
          sys.exit(1)
```

### Continue on Error
```yaml
- name: Optional notification
  module: shell
  with:
    cmd: python notify.py
  continue-on-error: true  # Won't fail the workflow
```

### Retry Logic with Backoff

`retry` retries a failing step; delays use **exponential backoff with jitter** (`base * 2^attempt`, capped at 5 minutes):

```yaml
- name: Flaky API call
  module: shell
  with:
    cmd: curl https://api.example.com
  retry: 3
  retry-delay: 5
```

Step failures report the **exit code**, the **stderr tail**, and a **per-attempt error list**:

```text
Step 'Flaky API call' failed after 4 attempt(s).
Last error: exit code 28 (stderr tail): Operation timed out
  Attempts: attempt 1: exit code 28: Operation timed out; attempt 2: exit code 28: Operation timed out; ...
If transient, increase 'retry' count. If permanent, fix the root cause before retrying.
```

### Branching on Outcome

Use `if:` to branch after a step: `success()`, `failure()`, `canceled()`, or `always()`. Combine with `retry` for an exploit attempt that retries, then loots on success or falls back on failure:

```yaml
steps:
  - name: exploit-attempt
    module: modules/exploit.py
    with:
      target: "{{ inputs.target }}"
    retry: 2
    retry-delay: 5

  - name: collect-loot
    module: shell
    if: success()
    with:
      cmd: ./loot.sh

  - name: fallback-exploit
    module: modules/fallback_exploit.py
    if: failure()
    with:
      target: "{{ inputs.target }}"
```

---

## ✅ Best Practices

### 1. Descriptive Step Names
```yaml
# ✅ Good
- name: Scan target for open HTTP/HTTPS ports
  module: shell
  with:
    cmd: nmap -p 80,443,8080 {{ inputs.target }}

# ❌ Bad
- name: scan
  module: shell
  with:
    cmd: nmap {{ inputs.target }}
```

### 2. Use Dynamic Paths
```yaml
# ✅ Good
- module: shell
  with:
    cmd: cp scan.txt {{ ctx.output_path }}/scan_{{ ctx.run_id }}.txt

# ❌ Bad
- module: shell
  with:
    cmd: cp scan.txt /tmp/scan.txt
```

### 3. Appropriate Timeouts
```yaml
- name: Quick ping
  module: shell
  with:
    cmd: ping -c 1 {{ inputs.target }}
  timeout: 1

- name: Full port scan
  module: shell
  with:
    cmd: nmap -p- {{ inputs.target }}
  timeout: 60
```

### 4. Separate Critical and Optional Steps
```yaml
- name: Critical validation
  module: shell
  with:
    cmd: python validate.py
  # Fails workflow if validation fails

- name: Optional notification
  module: shell
  with:
    cmd: python notify.py
  continue-on-error: true
```

---

## 📖 Examples

### Sequential Processing
```yaml
jobs:
  process:
    steps:
      - name: Install tools
        module: shell
        with:
          cmd: uv_install python-nmap
      
      - name: Run scan
        module: python
        with:
          script: |
            import nmap
            nm = nmap.PortScanner()
            nm.scan("{{ inputs.target }}", "22-443")
            print(nm.csv())

      - name: Save status
        module: shell
        with:
          cmd: echo "Complete" > {{ ctx.output_path }}/status.txt
```

### Parallel Jobs with Dependencies
```yaml
jobs:
  scan_tcp:
    steps:
      - module: shell
        with:
          cmd: nmap -sS {{ inputs.target }} -oX tcp.xml
  
  scan_udp:
    steps:
      - module: shell
        with:
          cmd: nmap -sU {{ inputs.target }} -oX udp.xml
  
  analyze:
    needs: [scan_tcp, scan_udp]  # Waits for both
    steps:
      - module: shell
        with:
          cmd: python analyze.py tcp.xml udp.xml
```

### Conditional Flow
```yaml
jobs:
  check:
    steps:
      - name: Verify target is reachable
        module: shell
        with:
          cmd: ping -c 1 {{ inputs.target }}
  
  exploit:
    needs: [check]  # Only runs if check succeeds
    steps:
      - module: shell
        with:
          cmd: python exploit.py {{ inputs.target }}
```

---

## ➡️ See Also

- [**Workflows**](workflows.md) — Workflow structure
- [**Templates**](templates.md) — Template functions
- [**CLI Reference**](../cli/commands.md) — Running workflows
