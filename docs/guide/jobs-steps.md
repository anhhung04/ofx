# Jobs & Steps

> Jobs run in parallel (unless dependent), steps run sequentially within a job

---

## 📦 Jobs Overview

Jobs are the main execution units in a workflow:

```yaml
jobs:
  scan:
    needs: []                  # Dependencies (empty = parallel)
    continue_on_error: false   # Stop workflow on failure
    envs:
      LOG_LEVEL: INFO          # Job-wide environment
    steps:
      - run: nmap {{ inputs.target }}
```

### Job Properties

| Property | Type | Description |
|----------|------|-------------|
| `steps` | list | **Required.** Steps to execute |
| `needs` | list | Job dependencies (for ordering) |
| `continue_on_error` | bool | Don't fail workflow if job fails |
| `envs` | dict | Environment variables for all steps |
| `hooks` | dict | Job lifecycle events |

---

## 📝 Steps Overview

Each step executes exactly **one** action:

| Action | Description |
|--------|-------------|
| `run` | Shell command |
| `script` | Python code block |


### Step Properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `name` | str | - | Descriptive name |
| `run` / `script` | str | - | **Required.** Action to execute |
| `timeout` | int | 30 | Max duration (minutes) |
| `retry` | int | 0 | Retry attempts on failure |
| `retry_delay` | int | 5 | Seconds between retries |
| `continue_on_error` | bool | false | Continue on failure |
| `envs` | dict | {} | Step environment variables |
| `working_directory` | str | - | Execution directory |

---

## 🖥️ Shell Commands (`run`)

```yaml
steps:
  - name: Port scan
    run: nmap -p {{ inputs.ports }} {{ inputs.target }}
    timeout: 30
    retry: 1
    retry_delay: 5
    envs:
      MODE: fast
    working_directory: ./scans
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
- [**Hooks**](hooks.md) — Lifecycle events
- [**CLI Reference**](../cli/commands.md) — Running workflows
