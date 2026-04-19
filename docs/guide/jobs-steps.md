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
    run_if: success()          # Optional conditional
    env:
      LOG_LEVEL: INFO          # Job-wide environment
    steps:
      - run: nmap {{ inputs.target }}
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
> See [Job model code](https://github.com/anhhung04/ofx/blob/main/src/ofx/models/job.py) for job model code.

---

## Steps Overview

Each step executes exactly **one** action:

| Action | Description |
|--------|-------------|
| `run` | Shell command |
| `script` | Inline Python code |
| `script_file` | Python file path |
| `uses` | Reusable workflow reference |
| `task` | Pre-built security tool wrapper (see [Tasks](tasks.md)) |


### Step Properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `name` | str | - | Descriptive name |
| `run` / `script` / `script_file` / `uses` / `task` | str | - | **Required.** Exactly one action |
| `timeout` | int/str | 1440 | Max duration in minutes (supports Jinja2 expressions) |
| `retry` | int | 0 | Retry attempts on failure |
| `retry-delay` | int | 5 | Seconds between retries |
| `continue-on-error` | bool | false | Continue on failure |
| `if` | bool\|str | true | Conditional execution |
| `env` | dict | {} | Step environment variables |
| `shell` | str | /bin/bash | Shell for `run`/`script` |
| `working-directory` | str | cwd | Execution directory |
| `log-stdout` | bool\|str | false | Save stdout to output logs |
| `interactive` | bool | false | Interactive mode (single-job stages only) |
| `with` | dict | {} | Inputs for `uses` / options+target for `task` |
| `secrets` | dict\|"inherit" | {} | Secrets for `uses` |
| `store-creds` | bool | null | Auto-store `UserAccount` credentials from task outputs |

---

## 🖥️ Shell Commands (`run`)

```yaml
steps:
  - name: Port scan
    run: nmap -p {{ inputs.ports }} {{ inputs.target }}
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
  run: |
    echo "Starting scan..."
    nmap -sS {{ inputs.target }} -oX scan.xml
    mv scan.xml {{ ctx.output_path }}/
```

---

## 🐍 Python Scripts (`script`)

```yaml
steps:
  - name: Process data
    script: |
      import json
      
      data = {"target": "{{ inputs.target }}"}
      with open("{{ ctx.output_path }}/data.json", "w") as f:
        json.dump(data, f)
```

### Python Script Files (`script_file`)

Execute an external Python script file. Paths are resolved relative to the workflow directory unless absolute.

```yaml
steps:
  - name: Run complex analysis
    script_file: scripts/analyze_results.py
    env:
      THRESHOLD: "0.95"
```

### Inter-Step Communication
```yaml
- name: Publish status
  script: |
    publish('status', {'state': 'running', 'progress': 50})
    
- name: Wait for config
  script: |
    config = wait_for('config', lambda d: d.get('ready'))
    print(f"Got config: {config}")
```

---

## 🔧 Task Steps (`task`)

Task steps run pre-built security tool wrappers with structured output parsing. The `with:` block provides the target and tool-specific options.

```yaml
steps:
  - task: nmap
    name: port-scan
    with:
      target: "{{ inputs.target }}"
      ports: "80,443,8080"
      version_detection: true

  - task: nuclei
    name: vuln-scan
    with:
      target: "{{ inputs.target }}"
      severity: "critical,high"
```

Task outputs are parsed into **typed objects** (Port, Url, Vulnerability, etc.) accessible via template helpers:

```yaml
  - run: |
      echo "Open ports: {{ ports(steps['port-scan'].outputs.typed_outputs) | length }}"
      echo "Vulns found: {{ vulns(steps['vuln-scan'].outputs.typed_outputs) | length }}"
```

See the [Tasks guide](tasks.md) for the full list of available tools and options.

---

## 📁 Working with Outputs

### Save to Output Directory
```yaml
- name: Save scan results
  run: nmap {{ inputs.target }} > {{ ctx.output_path }}/scan.txt
```

### Share Data Between Steps
```yaml
steps:
  - name: Generate data
    script: |
      import json
      data = {"ports": [80, 443, 8080]}
      with open("{{ ctx.output_path }}/data.json", "w") as f:
        json.dump(data, f)

  - name: Use data
    script: |
      import json
      with open("{{ ctx.output_path }}/data.json") as f:
        data = json.load(f)
      print(f"Ports: {data['ports']}")
```

### Output Variables with OFX_OUTPUTS
```yaml
- name: Export variables
  run: |
    echo "PORT=8080" >> $OFX_OUTPUTS
    echo "STATUS=ready" >> $OFX_OUTPUTS
```

---

## ⚠️ Error Handling

### Exit Codes
```yaml
- name: Check service
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
  run: python notify.py
  continue_on_error: true  # Won't fail the workflow
```

### Retry Logic
```yaml
- name: Flaky API call
  run: curl https://api.example.com
  retry: 3
  retry_delay: 5
```

---

## ✅ Best Practices

### 1. Descriptive Step Names
```yaml
# ✅ Good
- name: Scan target for open HTTP/HTTPS ports
  run: nmap -p 80,443,8080 {{ inputs.target }}

# ❌ Bad
- name: scan
  run: nmap {{ inputs.target }}
```

### 2. Use Dynamic Paths
```yaml
# ✅ Good
- run: cp scan.txt {{ ctx.output_path }}/scan_{{ ctx.run_id }}.txt

# ❌ Bad
- run: cp scan.txt /tmp/scan.txt
```

### 3. Appropriate Timeouts
```yaml
- name: Quick ping
  run: ping -c 1 {{ inputs.target }}
  timeout: 1

- name: Full port scan
  run: nmap -p- {{ inputs.target }}
  timeout: 60
```

### 4. Separate Critical and Optional Steps
```yaml
- name: Critical validation
  run: python validate.py
  # Fails workflow if validation fails

- name: Optional notification
  run: python notify.py
  continue_on_error: true
```

---

## 📖 Examples

### Sequential Processing
```yaml
jobs:
  process:
    steps:
      - name: Install tools
        run: uv_install python-nmap
      
      - name: Run scan
        script: |
          import nmap
          nm = nmap.PortScanner()
          nm.scan("{{ inputs.target }}", "22-443")
          print(nm.csv())
      
      - name: Save status
        run: echo "Complete" > {{ ctx.output_path }}/status.txt
```

### Parallel Jobs with Dependencies
```yaml
jobs:
  scan_tcp:
    steps:
      - run: nmap -sS {{ inputs.target }} -oX tcp.xml
  
  scan_udp:
    steps:
      - run: nmap -sU {{ inputs.target }} -oX udp.xml
  
  analyze:
    needs: [scan_tcp, scan_udp]  # Waits for both
    steps:
      - run: python analyze.py tcp.xml udp.xml
```

### Conditional Flow
```yaml
jobs:
  check:
    steps:
      - name: Verify target is reachable
        run: ping -c 1 {{ inputs.target }}
  
  exploit:
    needs: [check]  # Only runs if check succeeds
    steps:
      - run: python exploit.py {{ inputs.target }}
```

---

## ➡️ See Also

- [**Workflows**](workflows.md) — Workflow structure
- [**Templates**](templates.md) — Template functions
- [**CLI Reference**](../cli/commands.md) — Running workflows
