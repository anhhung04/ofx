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
run: echo "Ports: {{ steps.Scan.outputs.open_ports }}"
```

---

## Job outputs
Promote step outputs to the job level so other jobs can consume them:
```yaml
jobs:
  scan:
    steps:
      - name: scan-step
        run: ...
        outputs:
          result: "{{ step.stdout }}"
    outputs:
      scan_result: "{{ steps['scan-step'].outputs.result }}"
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

### Shell steps
```yaml
jobs:
  discover:
    outputs:
      target_ip: "{{ steps['find-target'].outputs.target_ip }}"
    steps:
      - name: find-target
        run: |
          target=$(dig +short example.com | head -1)
          echo "target_ip=$target" >> $OFX_OUTPUTS

  exploit:
    needs: [discover]
    steps:
      - run: echo "Attacking {{ jobs.discover.outputs.target_ip }}"
```

### Python script steps — `add_outputs()`

Python script steps have a built-in `add_outputs(**kwargs)` function that writes key-value pairs to the outputs file automatically:

```yaml
steps:
  - name: collect-results
    script: |
      subs = ["a.example.com", "b.example.com"]
      add_outputs(sub_count=len(subs), subs_file="/tmp/subs.txt")
```

Lists and dicts are automatically serialized as JSON:

```yaml
steps:
  - name: structured-output
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
- Use `typed_outputs` and template filters when chaining task results between jobs.
- In Python scripts, prefer `add_outputs(key=val)` over manual `OFX_OUTPUTS` file writes.

---

## Temp directory: `OFX_RUN_DIR`

Each workflow run gets a unique temp directory exposed as `$OFX_RUN_DIR`. Use it instead of hardcoded `/tmp` paths to avoid collisions when running workflows in parallel.

### Shell steps
```yaml
- run: |
    nmap -oG ${OFX_RUN_DIR:-/tmp}/ofx_scan.gnmap {{ inputs.target }}
    echo "scan_file=${OFX_RUN_DIR:-/tmp}/ofx_scan.gnmap" >> $OFX_OUTPUTS
```

### Python script steps
```yaml
- script: |
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

## Typed outputs (task steps)

When a step uses `task:`, OFX automatically parses the tool's output into **structured objects** stored in `step.outputs.typed_outputs`. Each object has a `_type` field indicating its kind.

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
# Get ports from a task step
ports: "{{ ports(steps['nmap-scan'].outputs.typed_outputs) }}"

# Get live URLs
urls: "{{ urls(steps['http-probe'].outputs.typed_outputs) | selectattr('status_code', 'gt', 0) }}"

# Count vulnerabilities
vuln_count: "{{ vulns(steps['nuclei-scan'].outputs.typed_outputs) | length }}"

# Get subdomains
subs: "{{ subdomains(steps['subfinder'].outputs.typed_outputs) | map(attribute='host') | list }}"
```

Available filter functions: `ports()`, `urls()`, `vulns()`, `subdomains()`, `ips()`, `tags()`, `records()`, `domains()`, `users()`, `of_type(items, type_name)`.

### Passing typed outputs between jobs

Expose typed outputs at the job level, then reference them downstream:

```yaml
jobs:
  scan:
    outputs:
      typed_outputs: "{{ steps['nmap-scan'].outputs.typed_outputs }}"
      live_hosts: "{{ steps.merge.outputs.live_hosts }}"
    steps:
      - task: nmap
        name: nmap-scan
        with:
          target: "{{ inputs.target }}"
      - name: merge
        script: |
          hosts = set()
          for item in {{ ports(steps["nmap-scan"].outputs.typed_outputs) | tojson }}:
              hosts.add(item.get('host', ''))
          add_outputs(live_hosts=chr(10).join(sorted(hosts)))

  exploit:
    needs: [scan]
    steps:
      - task: nuclei
        with:
          target: "{{ jobs.scan.outputs.live_hosts }}"
```

### Exporting typed outputs to a project

Use `export_typed_outputs()` in a script step to write structured results to the project directory:

```yaml
- name: export-to-project
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
