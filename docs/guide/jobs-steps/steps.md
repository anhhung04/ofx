# Steps

Steps are the smallest unit of execution in an OFX workflow. Each step runs a command, script, reusable workflow, or **task** (pre-built security tool wrapper) and can have its own environment and error handling.

---

## Step Syntax
```yaml
name: Example Workflow
jobs:
  example:
    name: Example Job
    steps:
      - name: Run Script
        run: ./myscript.sh
        env:
          VAR: value
        timeout: 10
        continue-on-error: true
```

---

## Step Fields
- `name`: (optional) Description of the step. **Must be unique within a job** — duplicate names cause a validation error.
- `run` / `script` / `script_file` / `uses` / `task`: **Exactly one** action per step
- `env`: (optional) Environment variables
- `timeout`: (optional) Max time in minutes (default: 1440). Supports Jinja2 expressions for dynamic scaling (see below).
- `retry`: (optional) Retry attempts on failure
- `retry_delay`: (optional) Seconds between retries (alias: `retry-delay`). Uses exponential backoff with jitter.
- `continue_on_error`: (optional) Continue even if this step fails (alias: `continue-on-error`). Outputs from the failed step are still accessible to later steps.
- `run_if`: (optional) Conditional execution (alias: `if`)
- `shell`: (optional) Shell for `run`/`script`
- `working_directory`: (optional) Execution directory (alias: `working-directory`)
- `log_stdout`: (optional) Save stdout to output logs (alias: `log-stdout`)
- `interactive`: (optional) Interactive mode (ignored for `uses`)
- `with`: (optional) Inputs for `uses` or options/target for `task` (model field: `run_with`)
- `secrets`: (optional) Secrets for `uses` (`inherit` to pass parent secrets)

### Dynamic Timeout

The `timeout` field accepts Jinja2 template expressions, enabling timeout scaling based on inputs or matrix values:

```yaml
steps:
  - name: scan-targets
    task: nmap
    with:
      target: "{{ inputs.targets_file }}"
    # Scale timeout: 15 min base + 1 min per 50 targets
    timeout: "{{ (inputs.target_count | int / 50) | int * 1 + 15 }}"
```

If the expression resolves to an invalid value, a default of 60 minutes is used with a warning.

---

## Advanced Usage
- Use `script:` to run inline Python code
- Use `script_file:` to execute an existing Python file (resolved relative to the workflow directory)
- Use `uses:` to call a reusable workflow
- Use `task:` to run a pre-built security tool wrapper (see [Tasks](../tasks.md))
- Use `if:` for conditional logic

---

## Task Steps

Task steps run pre-built tool wrappers that handle option mapping, execution, and output parsing automatically. The `with:` block must include `target` (or `targets`) plus any tool-specific options:

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
      tags: "cve"
```

**Multiple targets** — Use `targets` (plural) or a comma-separated string:

```yaml
  - task: httpx
    with:
      targets: "a.com,b.com,c.com"       # comma-separated
  - task: httpx
    with:
      targets: "{{ inputs.target_list }}"  # from workflow input
```

**Credential storage** — Task steps producing `UserAccount` outputs can auto-store them:

```yaml
  - task: maigret
    store-creds: true
    with:
      target: "username"
```

Task outputs include raw `stdout` and structured `typed_outputs` (Port, Url, Vulnerability, Certificate, Exploit, UserAccount, etc.) accessible via template helpers:

```yaml
  - run: |
      echo "Ports: {{ ports(steps['port-scan'].outputs.typed_outputs) | map(attribute='host_port') | join(', ') }}"
      echo "Vulns: {{ vulns(steps['vuln-scan'].outputs.typed_outputs) | length }}"
```

For the full list of available tasks and options, see the [Tasks guide](../tasks.md).

---

## Python Scripts and Inter-Job Communication

Steps can execute inline Python code using the `script` field. Python scripts have access to workflow context, environment variables, and special functions for inter-job communication.

### Available Variables in Scripts

Python scripts automatically have access to:
- `__job__`: The current job model object
- `__step__`: The current step model object  
- `__workflow__`: The current workflow model object
- `__ctx__`: The run context object

### Channel Communication Functions

Scripts can communicate between jobs using channel functions:

- `publish(channel, data)`: Publish data to a named channel
- `subscribe(channel)`: Returns a generator that yields data when it changes (auto-emit)
- `wait_for(channel, condition, timeout=60)`: Wait for data matching a condition

### Example: Inter-Job Communication
```yaml
name: Channel Communication Example
jobs:
  producer:
    steps:
      - name: Send data
        script: |
          publish('results', {'status': 'complete', 'data': [1, 2, 3]})
          
  consumer:
    needs: producer
    steps:
      - name: Receive data
        script: |
          # Wait for data
          data = wait_for('results', lambda d: d.get('status') == 'complete')
          print(f"Received: {data}")
          
      - name: Subscribe to changes
        script: |
          # Subscribe returns a generator
          gen = subscribe('results')
          for update in gen:
              print(f"Update: {update}")
              if update.get('status') == 'complete':
                  break
```

Channels are scoped to the workflow level and allow jobs to coordinate asynchronously.

---

## See Also
- [Jobs](jobs.md)
- [Outputs](outputs.md)
- [Script files](script-file.md)