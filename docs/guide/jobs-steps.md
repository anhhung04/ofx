# Jobs & Steps

Jobs are logical groupings of steps that execute sequentially. Steps are the smallest unit of execution, running individual commands or scripts.

## Jobs

### Basic Job Structure

```yaml
jobs:
  job_name:
    description: Optional job description
    steps:
      - name: Step 1
        run: echo "Hello"
      
      - name: Step 2
        run: echo "World"
```

### Job Properties

#### name (key)
The job identifier used for dependencies.

```yaml
jobs:
  reconnaissance:  # This is the name
    steps: [...]
```

#### description (optional)
Human-readable job description.

```yaml
jobs:
  scan:
    description: "Performs comprehensive port and service scanning"
    steps: [...]
```

#### needs (optional)
List of jobs that must complete before this job runs.

```yaml
jobs:
  scan:
    steps: [...]
  
  analyze:
    needs: [scan]  # Waits for scan job
    steps: [...]
  
  report:
    needs: [scan, analyze]  # Waits for both
    steps: [...]
```

#### continue_on_error (optional)
Continue workflow execution even if this job fails.

```yaml
jobs:
  optional_check:
    continue_on_error: true
    steps:
      - run: some_command_that_might_fail
```

#### envs (optional)
Environment variables specific to this job.

```yaml
jobs:
  build:
    envs:
      CC: gcc
      CFLAGS: -O2
    steps:
      - run: make build
```

#### hooks (optional)
Job-specific lifecycle hooks.

```yaml
jobs:
  deploy:
    hooks:
      on_start:
        script: echo "Starting deployment"
        language: shell
      on_success:
        script: python notify.py --status success
        language: shell
    steps: [...]
```

## Steps

### Basic Step Structure

```yaml
steps:
  - name: Step name
    run: command to execute
  
  - name: Another step
    script: |
      #!/bin/bash
      echo "Multi-line script"
      echo "Line 2"
    language: shell
```

### Step Properties

#### name (required)
Human-readable step name.

```yaml
- name: "Scan target for open ports"
  run: nmap ${{ inputs.target }}
```

#### run (option 1)
Single-line command to execute.

```yaml
- name: List files
  run: ls -la /tmp
```

#### script (option 2)
Multi-line script to execute.

```yaml
- name: Complex operation
  script: |
    #!/bin/bash
    for port in 80 443 8080; do
      nc -zv ${{ inputs.target }} $port
    done
  language: shell
```

#### language (required with script)
Script language: `shell`, `python`, `bash`, `sh`.

```yaml
- name: Python script
  script: |
    import os
    print(f"Running in {os.getcwd()}")
  language: python
```

#### working_dir (optional)
Working directory for command execution.

```yaml
- name: Build project
  run: make build
  working_dir: /tmp/project
```

#### envs (optional)
Environment variables for this step.

```yaml
- name: Compile with specific flags
  run: gcc main.c -o app
  envs:
    CFLAGS: -O3 -Wall
    LDFLAGS: -lpthread
```

#### timeout (optional)
Maximum execution time in seconds.

```yaml
- name: Long running scan
  run: nmap -p- ${{ inputs.target }}
  timeout: 3600  # 1 hour
```

#### retry (optional)
Number of retry attempts on failure.

```yaml
- name: API call with retry
  run: curl https://api.example.com
  retry: 3
  retry_delay: 5  # seconds between retries
```

#### continue_on_error (optional)
Continue to next step even if this step fails.

```yaml
- name: Optional cleanup
  run: rm -f /tmp/cache
  continue_on_error: true
```

#### hooks (optional)
Step-specific lifecycle hooks.

```yaml
- name: Critical operation
  run: python important.py
  hooks:
    on_start:
      script: echo "Starting critical step"
      language: shell
    on_error:
      script: python alert_team.py --step failed
      language: python
```

## Command Execution

### Shell Commands

```yaml
- name: Basic shell command
  run: echo "Hello World"

- name: Pipe commands
  run: cat file.txt | grep "pattern" | wc -l

- name: Command substitution
  run: echo "Current user is $(whoami)"
```

### Python Scripts

```yaml
- name: Inline Python
  script: |
    import sys
    import json
    
    data = {"status": "success", "value": 42}
    print(json.dumps(data))
  language: python

- name: Python with external script
  run: python /path/to/script.py --arg value
```

### Bash Scripts

```yaml
- name: Bash script with functions
  script: |
    #!/bin/bash
    
    function check_port() {
      local port=$1
      nc -zv ${{ inputs.target }} $port
    }
    
    check_port 80
    check_port 443
  language: bash
```

## Using OFX APIs in Steps

### Python API Example

```yaml
- name: Port scanning with OFX API
  script: |
    from ofx.api import PortScanner
    
    scanner = PortScanner(
        target='${{ inputs.target }}',
        ports='1-1000'
    )
    
    results = scanner.scan()
    print(f"Open ports: {results}")
  language: python
```

### Shellcode Generation

```yaml
- name: Generate shellcode
  script: |
    from ofx.api import shellcode
    
    code = shellcode.generate(
        platform='linux',
        arch='x64',
        payload='reverse_shell',
        lhost='${{ inputs.lhost }}',
        lport='${{ inputs.lport }}'
    )
    
    with open('payload.bin', 'wb') as f:
      f.write(code)
  language: python
```

### Web Shell Client

```yaml
- name: Execute command via webshell
  script: |
    from ofx.api.webshell import WebShellClient
    
    client = WebShellClient(
        url='${{ inputs.webshell_url }}',
        password='${{ secrets.SHELL_PASSWORD }}'
    )
    
    result = client.execute('whoami')
    print(result)
  language: python
```

## Tool Installation

OFX provides helper functions for installing tools:

### UV Package Manager

```yaml
- name: Install Python packages
  run: ${{ uv_install('requests beautifulsoup4') }}

- name: Use installed package
  script: |
    import requests
    response = requests.get('https://example.com')
    print(response.status_code)
  language: python
```

### Go Tools

```yaml
- name: Install Go tool
  run: ${{ go_install('github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest') }}

- name: Run nuclei
  run: ${{ tools_bin_dir }}/nuclei -target ${{ inputs.target }}
```

### Pip Packages

```yaml
- name: Install with pip
  run: ${{ pip_install('scapy') }}
```

### Cargo (Rust)

```yaml
- name: Install Rust tool
  run: ${{ cargo_install('ripgrep') }}
```

## File Operations

### Reading Files

```yaml
- name: Process configuration
  script: |
    import yaml
    
    with open('${{ ctx.output_path }}/config.yml') as f:
      config = yaml.safe_load(f)
    
    print(f"Target: {config['target']}")
  language: python
```

### Writing Files

```yaml
- name: Generate report
  script: |
    with open('${{ ctx.output_path }}/report.txt', 'w') as f:
      f.write(f"Scan completed for {ctx.inputs['target']}\n")
      f.write(f"Results saved to {ctx.output_path}\n")
  language: python
```

### File Manipulation

```yaml
- name: Organize results
  run: |
    mkdir -p ${{ ctx.output_path }}/scans
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
  run: python ${{ ctx.workflow_dir }}/scripts/analyze.py --input ${{ ctx.output_path }}
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
