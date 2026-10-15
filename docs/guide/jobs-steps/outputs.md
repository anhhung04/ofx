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
    module: shell
    with:
      cmd: nmap {{ inputs.target }}
    outputs:
      open_ports: "{{ step.stdout_lines }}"
```

Use them later in the same job:
```yaml
module: shell
with:
  cmd: 'echo "Ports: {{ steps.Scan.outputs.open_ports }}"'
```

---

## Job outputs
Promote step outputs to the job level so other jobs can consume them:
```yaml
jobs:
  scan:
    steps:
      - name: scan-step
        module: shell
        with:
          cmd: ...
        outputs:
          result: "{{ step.stdout }}"
    outputs:
      scan_result: "{{ steps['scan-step'].outputs.result }}"
```

Reference job outputs from dependents:
```yaml
module: shell
with:
  cmd: 'echo "Scan: {{ jobs.scan.outputs.scan_result }}"'
```

### Outputs from Failed Steps

When a step has `continue-on-error: true` and fails, its outputs (stdout, stderr, and any `OFX_OUTPUTS` written before failure) are still saved to the registry. Later steps can reference them normally:

```yaml
steps:
  - name: optional-check
    module: shell
    with:
      cmd: |
        echo "result=partial" >> $OFX_OUTPUTS
        exit 1  # fails, but output is preserved
    continue-on-error: true

  - name: use-result
    module: shell
    with:
      cmd: echo "Got {{ steps['optional-check'].outputs.result }}"
```

Without `continue-on-error`, failed step outputs are **not** preserved.

---

## Dynamic outputs with `OFX_OUTPUTS`
For commands that discover values at runtime, write key/value pairs to the temp file exposed via the `OFX_OUTPUTS` environment variable.

How it works for each command step:
1. OFX creates a temp file and sets `OFX_OUTPUTS` to its path.
2. Your command writes `key=value` lines to that file.
3. After the command finishes, OFX parses the file into `step.outputs`.
4. The temp file is removed automatically.

### Shell steps
```yaml
jobs:
  discover:
    outputs:
      target_ip: "{{ steps['find-target'].outputs.target_ip }}"
    steps:
      - name: find-target
        module: shell
        with:
          cmd: |
            target=$(dig +short example.com | head -1)
            echo "target_ip=$target" >> $OFX_OUTPUTS

  exploit:
    needs: [discover]
    steps:
      - module: shell
        with:
          cmd: echo "Attacking {{ jobs.discover.outputs.target_ip }}"
```

### Python module steps — `add_outputs()`

Python module steps have a built-in `add_outputs(**kwargs)` function that writes key-value pairs to the outputs file automatically:

```yaml
steps:
  - name: collect-results
    module: python
    with:
      script: |
        subs = ["a.example.com", "b.example.com"]
        add_outputs(sub_count=len(subs), subs_file="/tmp/subs.txt")
```

Lists and dicts are automatically serialized as JSON:

```yaml
steps:
  - name: structured-output
    module: python
    with:
      script: |
        hosts = ["10.0.0.1", "10.0.0.2"]
        metadata = {"scan_type": "full", "ports": [22, 80, 443]}
        add_outputs(hosts=hosts, metadata=metadata)
        # hosts=["10.0.0.1","10.0.0.2"]
        # metadata={"scan_type":"full","ports":[22,80,443]}
```

You can also use `**kwargs` expansion:

```yaml
steps:
  - name: export-all
    module: python
    with:
      script: |
        results = {"host": "10.0.0.1", "port": "22", "service": "ssh"}
        add_outputs(**results)
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
- Use `typed_outputs` and template filters when chaining module results between jobs.
- In Python modules, prefer `add_outputs(key=val)` over manual `OFX_OUTPUTS` file writes.

---

## Temp directory: `OFX_RUN_DIR`

Each workflow run gets a unique temp directory exposed as `$OFX_RUN_DIR`. Use it instead of hardcoded `/tmp` paths to avoid collisions when running workflows in parallel.

### Shell steps
```yaml
- module: shell
  with:
    cmd: |
      nmap -oG ${OFX_RUN_DIR:-/tmp}/ofx_scan.gnmap {{ inputs.target }}
      echo "scan_file=${OFX_RUN_DIR:-/tmp}/ofx_scan.gnmap" >> $OFX_OUTPUTS
```

### Python module steps
```yaml
- module: python
  with:
    script: |
      import os
      run_dir = os.environ.get("OFX_RUN_DIR", "/tmp")
      out_file = f"{run_dir}/ofx_results.txt"
      Path(out_file).write_text(data)
      add_outputs(result_file=out_file)
```

The directory is cleaned up automatically after the workflow finishes.

---

## Stdout display truncation

By default, OFX shows the first **50 lines** of stdout/stderr in the console. Longer output is truncated with a notice:

```
... [950 more lines — full output saved to logs]
```

The full output is always saved to log files when `log-stdout: true` is set. Configure the limit:

```yaml
# ~/.ofx/config.yml
max_display_lines: 100
```

Or via environment variable: `OFX_MAX_DISPLAY_LINES=100`

---

## Logging and capturing output

### Step log files

- `log-stdout: true` saves the full stdout of a step to `stdout_<job>_<step>.log` under the run's `logs/` directory (the log also records the resolved command/script and truncation flags).
- `log-command: true` logs the resolved command or script itself before the step executes — useful for auditing what actually ran after template resolution.

```yaml
steps:
  - name: auth-bypass
    module: shell
    with:
      cmd: curl -s -X POST -d "user=admin&pass={{ secrets.ADMIN_PW }}" https://{{ inputs.target }}/login
    log-command: true
    log-stdout: true
```

After the run, the full command output is available at `logs/stdout_auth-job_auth-bypass.log`.

### Captured output keys

Every step exposes:

- `{{ steps.<name>.outputs.exit_code }}` — process exit code (0 on success)
- `{{ steps.<name>.outputs.stdout }}` / `{{ steps.<name>.outputs.stderr }}` — captured streams (also via `{{ steps.<name>.stdout }}`)
- `{{ steps.<name>.outputs.<key> }}` — every key written via `$OFX_OUTPUTS`, `add_outputs()`, or a UDF module's returned dict

### Feeding module output into a later step

Module output flows into the next step's `with:` arguments through templating — no manual copy step needed:

```yaml
steps:
  - name: find-target
    module: shell
    with:
      cmd: |
        target=$(dig +short {{ inputs.domain }} | head -1)
        echo "target_ip=$target" >> $OFX_OUTPUTS

  - name: scan-target
    module: shell
    with:
      cmd: nmap -sV {{ steps['find-target'].outputs.target_ip }}

  - name: analyze
    module: modules/port_scan.py
    with:
      target: "{{ steps['scan-target'].outputs.stdout | regex_search('[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+') }}"
```

Here `find-target` writes `target_ip` to its outputs via `OFX_OUTPUTS`, `scan-target` reads it from the registry into its own `cmd`, and `analyze` passes the previous step's stdout (filtered by a regex helper) into its `with:` arguments.

---

## Typed outputs

Modules can emit **structured objects** — dicts tagged with a `_type` field — stored in `step.outputs.typed_outputs`. A Python module writes them with `add_outputs(typed_outputs=[...])`; a user-defined module does the same via `ctx.add_outputs()`:

```python
# modules/port_scan.py
def run(ctx):
    import re, subprocess
    target = ctx.inputs["target"]
    ports = ctx.inputs.get("ports", "1-1000")
    out = subprocess.run(["nmap", "-p", ports, "-oG", "-", target],
                         capture_output=True, text=True).stdout
    parsed = []
    for line in out.splitlines():
        m = re.match(r"^(\S+)\s+(\d+)/open", line)
        if m:
            parsed.append({"_type": "port", "host": m.group(1),
                           "port": int(m.group(2)), "state": "open"})
    ctx.add_outputs(typed_outputs=parsed)
    return {"port_count": len(parsed)}
```

```yaml
steps:
  - module: modules/port_scan.py
    name: nmap-scan
    with:
      target: "{{ inputs.target }}"
```

Each typed object has a `_type` field indicating its kind.

### Output types

| Type | Description | Key fields |
|------|------------|------------|
| `port` | Open port | `host`, `port`, `protocol`, `service_name` |
| `url` | Discovered URL | `url`, `host`, `status_code`, `title` |
| `vulnerability` | Finding | `name`, `severity`, `url`, `matched_at` |
| `subdomain` | Subdomain | `host`, `source` |
| `ip` | IP address | `ip`, `host` |
| `tag` | Metadata tag | `name`, `value`, `category` |
| `record` | DNS record | `host`, `type`, `value` |
| `domain` | Domain info | `domain`, `registrar`, `created_date` |
| `certificate` | TLS cert | `host`, `issuer`, `subject`, `not_after` |
| `exploit` | Known exploit | `name`, `id`, `platform` |
| `user_account` | Credential | `username`, `password`, `hash` |

### Using typed outputs in templates

Filter typed outputs with built-in helper functions:

```yaml
# Get ports from a scan module
ports: "{{ ports(steps['nmap-scan'].outputs.typed_outputs) }}"

# Get live URLs
urls: "{{ urls(steps['http-probe'].outputs.typed_outputs) | selectattr('status_code', 'gt', 0) }}"

# Count vulnerabilities
vuln_count: "{{ vulns(steps['nuclei-scan'].outputs.typed_outputs) | length }}"

# Get subdomains
subs: "{{ subdomains(steps['subfinder'].outputs.typed_outputs) | map(attribute='host') | list }}"
```

Available filter functions: `ports()`, `urls()`, `vulns()`, `subdomains()`, `ips()`, `tags()`, `records()`, `domains()`, `users()`, `certs()`, `exploits()`, `of_type(items, type_name)`.

### Passing typed outputs between jobs

Expose typed outputs at the job level, then reference them downstream:

```yaml
jobs:
  scan:
    outputs:
      typed_outputs: "{{ steps['nmap-scan'].outputs.typed_outputs }}"
      live_hosts: "{{ steps.merge.outputs.live_hosts }}"
    steps:
      - module: modules/port_scan.py
        name: nmap-scan
        with:
          target: "{{ inputs.target }}"
      - name: merge
        module: python
        with:
          script: |
            hosts = set()
            for item in {{ ports(steps["nmap-scan"].outputs.typed_outputs) | tojson }}:
                hosts.add(item.get('host', ''))
            add_outputs(live_hosts=chr(10).join(sorted(hosts)))

  exploit:
    needs: [scan]
    steps:
      - module: modules/vuln_scan.py
        with:
          target: "{{ jobs.scan.outputs.live_hosts }}"
```

### Exporting typed outputs to a project

Use `export_typed_outputs()` in a python module to write structured results to the project directory:

```yaml
- name: export-to-project
  module: python
  with:
    script: |
      project = '{{ vars.project_path | default("", true) }}'
      if project:
          all_typed = {{ jobs['scan'].outputs.typed_outputs | default([], true) | tojson }}
          summaries = export_typed_outputs(project, all_typed)
          for s in summaries:
              print(s)
  continue-on-error: true
```

---

## Workflow-level outputs

Promote job outputs to the workflow level for use by callers or `uses:` references:

```yaml
name: my-scan
outputs:
  live_hosts: "${{ jobs.scan.outputs.live_hosts }}"
  vuln_count: "${{ jobs.vuln.outputs.vuln_count }}"

jobs:
  scan:
    outputs:
      live_hosts: "{{ steps.merge.outputs.live_hosts }}"
    steps: ...
  vuln:
    outputs:
      vuln_count: "{{ steps.count.outputs.vuln_count }}"
    steps: ...
```

---

## See also
- [Steps](steps.md)
- [Jobs](jobs.md)
