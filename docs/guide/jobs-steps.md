# Jobs & Steps

Jobs group steps; jobs in the same stage run in parallel, steps inside a job run sequentially.

## Jobs (key fields)

```yaml
jobs:
  scan:
    needs: []           # dependencies; missing = parallel
    continue_on_error: false
    envs: { LOG_LEVEL: INFO }
    steps: [...]        # required
```

- `needs`: order jobs; parallel if omitted.
- `continue_on_error`: keep running later stages if this job fails.
- `envs`: job-wide env vars.

## Steps (one action each)

Exactly one of `run`, `script`, or `uses`.

```yaml
- name: run command
  run: nmap -p ${{ inputs.ports }} ${{ inputs.target }}
  timeout: 30       # minutes
  retry: 1
  retry_delay: 5
  continue_on_error: false
  envs: { MODE: fast }
  working_directory: ./scans
  hooks:
    before_step: { script: echo "starting" }

- name: multi-line script
  script: |
    #!/bin/bash
    echo "$TARGET"
  envs: { TARGET: ${{ inputs.target }} }
```

## Nested workflow

```yaml
- name: reuse workflow
  uses: ./subflow.yml
  run_with: { target: ${{ inputs.target }} }
  secrets: inherit
```

## Outputs

Use `${{ ctx.output_path }}` for files; set structured outputs from steps with `OFX_OUTPUTS` in your command or script.

## Handy template helpers

- `${{ tools_bin_dir }}` for installed tool binaries.
- `${{ uv_install('pkg1 pkg2') }}` / `${{ go_install('module@latest') }}` for quick installs.

See also: [templates](templates.md) for `${{ }}` rendering and [hooks](hooks.md) for step lifecycle triggers.
    mv *.xml ${{ ctx.output_path }}/scans/
    tar -czf ${{ ctx.output_path }}/results.tar.gz ${{ ctx.output_path }}/scans
```

## Working with Job Output

### Capturing Output

```yaml
- name: Save scan results
  run: nmap ${{ inputs.target }} > ${{ ctx.output_path }}/scan.txt

- name: Parse scan results
  script: |
    with open('${{ ctx.output_path }}/scan.txt') as f:
      content = f.read()
      if '22/tcp open' in content:
        print("SSH is available")
  language: python
```

### Sharing Data Between Steps

Use the output directory:

```yaml
steps:
  - name: Generate data
    script: |
      import json
      data = {"ports": [80, 443, 8080]}
      with open('${{ ctx.output_path }}/data.json', 'w') as f:
        json.dump(data, f)
    language: python
  
  - name: Use data
    script: |
      import json
      with open('${{ ctx.output_path }}/data.json') as f:
        data = json.load(f)
      print(f"Scanning ports: {data['ports']}")
    language: python
```

## Error Handling

### Exit Codes

```yaml
- name: Check service
  script: |
    import sys
    import socket
    
    try:
      s = socket.socket()
      s.connect(('${{ inputs.target }}', 80))
      print("Service is up")
      sys.exit(0)
    except:
      print("Service is down")
      sys.exit(1)
  language: python
```

### Try-Catch in Steps

```yaml
- name: Safe operation
  script: |
    try:
      # Risky operation
      result = dangerous_function()
      print(f"Success: {result}")
    except Exception as e:
      print(f"Error occurred: {e}")
      # Don't exit with error code if you want to continue
  language: python
  continue_on_error: true
```

## Best Practices

### 1. Descriptive Step Names

```yaml
# Good
- name: "Scan target for open HTTP/HTTPS ports"
  run: nmap -p 80,443,8080,8443 ${{ inputs.target }}

# Bad
- name: "scan"
  run: nmap ${{ inputs.target }}
```

### 2. Use Templates for Dynamic Values

```yaml
# Good
- name: Save results
  run: cp scan.txt ${{ ctx.output_path }}/scan_${{ ctx.run_id }}.txt

# Bad
- name: Save results
  run: cp scan.txt /tmp/scan.txt  # Hardcoded path
```

### 3. Handle Errors Appropriately

```yaml
- name: Critical validation
  run: python validate.py
  # Fails workflow if validation fails

- name: Optional notification
  run: python notify.py
  continue_on_error: true  # Doesn't fail workflow
```

### 4. Use Appropriate Timeouts

```yaml
- name: Quick check
  run: ping -c 1 ${{ inputs.target }}
  timeout: 5

- name: Full scan
  run: nmap -p- ${{ inputs.target }}
  timeout: 3600  # 1 hour for complete scan
```

### 5. Organize Complex Scripts

```yaml
# For complex logic, use external scripts
- name: Complex analysis
  run: python ${{ ctx.workflow_dirs }}/scripts/analyze.py --input ${{ ctx.output_path }}
```

## Examples

### Sequential Steps

```yaml
jobs:
  setup_and_scan:
    steps:
      - name: Install tools
        run: ${{ uv_install('python-nmap') }}
      
      - name: Run scan
        script: |
          import nmap
          nm = nmap.PortScanner()
          nm.scan('${{ inputs.target }}', '22-443')
          print(nm.csv())
        language: python
      
      - name: Save results
        run: echo "Scan complete" > ${{ ctx.output_path }}/status.txt
```

### Conditional Execution

```yaml
jobs:
  conditional_scan:
    steps:
      - name: Check if target is up
        run: ping -c 1 ${{ inputs.target }}
        continue_on_error: false
      
      - name: Full scan
        run: nmap -sS -sV -A ${{ inputs.target }}
        # Only runs if ping succeeds
```

### Parallel Jobs with Sequential Steps

```yaml
jobs:
  scan_tcp:
    steps:
      - name: TCP SYN scan
        run: nmap -sS ${{ inputs.target }}
      
      - name: Analyze TCP results
        run: python analyze_tcp.py
  
  scan_udp:
    steps:
      - name: UDP scan
        run: nmap -sU ${{ inputs.target }}
      
      - name: Analyze UDP results
        run: python analyze_udp.py
  
  # Both jobs run in parallel, steps within each job run sequentially
```

## See Also

- [Workflows](workflows.md) - Workflow configuration
- [Hooks System](hooks.md) - Lifecycle hooks
- [Templates](templates.md) - Template functions
- [CLI Commands](../cli/commands.md) - Running workflows
