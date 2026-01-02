# Workflows

Workflows are the top-level execution containers in OFX. They define the complete execution flow including jobs, dependencies, inputs, secrets, and lifecycle hooks.

## Basic Structure

```yaml
name: My Workflow
description: Optional workflow description

inputs:
  target:
    description: Target hostname or IP
    required: true
    default: localhost

secrets:
  API_KEY:
    description: API key for external services
    required: false

jobs:
  reconnaissance:
    steps:
      - name: Scan ports
        run: nmap -sV ${{ inputs.target }}
  
  analysis:
    needs: [reconnaissance]
    steps:
      - name: Analyze results
        run: python analyze.py
```

## Workflow Properties

### name (required)
Human-readable workflow name.

```yaml
name: Red Team Assessment
```

### description (optional)
Detailed description of what the workflow does.

```yaml
description: Automated reconnaissance and vulnerability assessment workflow
```

### inputs (optional)
Define input parameters that can be provided at runtime.

```yaml
inputs:
  target:
    description: Target hostname or IP address
    required: true
    default: example.com
  
  ports:
    description: Ports to scan
    required: false
    default: "80,443,8080"
```

Access inputs in commands using `${{ inputs.name }}`:

```yaml
run: nmap -p ${{ inputs.ports }} ${{ inputs.target }}
```

### secrets (optional)
Define sensitive configuration values.

```yaml
secrets:
  API_KEY:
    description: API key for Shodan
    required: true
  
  API_SECRET:
    description: API secret
    required: false
```

Access secrets using `${{ secrets.name }}`:

```yaml
run: python scan.py --api-key ${{ secrets.API_KEY }}
```

### envs (optional)
Define environment variables for the entire workflow.

```yaml
envs:
  LOG_LEVEL: DEBUG
  OUTPUT_DIR: /tmp/results
```

### jobs (required)
Map of job definitions. See [Jobs & Steps](jobs-steps.md) for details.

## Running Workflows

### From Command Line

```bash
# Basic execution
ofx flow run workflow.yml

# With inputs
ofx flow run workflow.yml --input target=192.168.1.1 --input ports=80,443

# With secrets
ofx flow run workflow.yml --secret API_KEY=your_key_here

# With environment variables
ofx flow run workflow.yml --env LOG_LEVEL=DEBUG
```

### From Python

```python
import asyncio
from pathlib import Path
from ofx.runner import WorkflowRunner, RunContext
from ofx.models.workflow import Workflow
import yaml

async def run_workflow():
    # Load workflow
    with open("workflow.yml") as f:
        workflow_data = yaml.safe_load(f)
    
    workflow = Workflow(**workflow_data)
    
    # Create context
    ctx = RunContext(
        inputs={"target": "192.168.1.1"},
        secrets={"API_KEY": "your_key"},
        output_path=Path("./output"),
    )
    
    # Run workflow
    runner = WorkflowRunner(workflow, ctx)
    result = await runner.run()
    
    print(f"Status: {result.status}")
    print(f"Output: {result.output}")

asyncio.run(run_workflow())
```

## Workflow Validation

Validate workflow syntax before running:

```bash
ofx flow validate workflow.yml
```

This checks:
- YAML syntax
- Required fields
- Job dependencies
- Input/secret references

## Workflow Dependencies

Jobs can depend on other jobs using the `needs` field:

```yaml
jobs:
  scan:
    steps:
      - name: Port scan
        run: nmap -sV ${{ inputs.target }}
  
  analyze:
    needs: [scan]  # Waits for scan to complete
    steps:
      - name: Analyze results
        run: python analyze.py
  
  report:
    needs: [analyze]  # Waits for analyze to complete
    steps:
      - name: Generate report
        run: python report.py
```

### Parallel Execution

Jobs without dependencies run in parallel:

```yaml
jobs:
  scan_http:
    steps:
      - run: nikto -h ${{ inputs.target }}
  
  scan_ssl:
    steps:
      - run: sslscan ${{ inputs.target }}
  
  # Both scan_http and scan_ssl run simultaneously
```

### Multiple Dependencies

Jobs can depend on multiple other jobs:

```yaml
jobs:
  port_scan:
    steps:
      - run: nmap ${{ inputs.target }}
  
  dns_enum:
    steps:
      - run: dnsrecon -d ${{ inputs.target }}
  
  exploit:
    needs: [port_scan, dns_enum]  # Waits for both to complete
    steps:
      - run: python exploit.py
```

## Workflow Hooks

Add hooks to execute custom code at various lifecycle points:

```yaml
name: Workflow with Hooks

hooks:
  on_start:
    script: |
      print(f"Starting workflow at {datetime.now()}")
      print(f"Target: {ctx.inputs['target']}")
    script:
  
  on_success:
    script: echo "Workflow completed successfully!"
    language: shell
  
  on_error:
    script: |
      import sys
      print(f"Error occurred: {error}", file=sys.stderr)
    script:

jobs:
  # ... job definitions
```

See [Hooks System](hooks.md) for complete documentation.

## Template Variables

Workflows support Jinja2 templates with `${{ }}` syntax:

```yaml
jobs:
  scan:
    steps:
      - name: Scan target
        run: nmap -p ${{ inputs.ports }} ${{ inputs.target }}
      
      - name: Save results
        run: cp results.txt ${{ ctx.output_path }}/scan_${{ ctx.run_id }}.txt
```

Available template variables:
- `${{ inputs.name }}` - Input values
- `${{ secrets.name }}` - Secret values
- `${{ ctx.output_path }}` - Output directory path
- `${{ ctx.run_id }}` - Unique run identifier
- `${{ tools_dir }}` - Tool installation directory
- `${{ tools_bin_dir }}` - Tool binaries directory

See [Templates](templates.md) for more details.

## Output Management

Workflows automatically create output directories:

```yaml
jobs:
  scan:
    steps:
      - name: Save scan results
        run: nmap ${{ inputs.target }} -oX ${{ ctx.output_path }}/scan.xml
```

Output structure:
```
output/
└── <run_id>/
    └── scan.xml
```

## Error Handling

### Continue on Error

By default, workflows stop on first error. Continue execution:

```yaml
jobs:
  scan:
    continue_on_error: true
    steps:
      - run: nmap ${{ inputs.target }}
```

### Retry Logic

Steps can be retried on failure:

```yaml
jobs:
  api_call:
    steps:
      - name: Call API
        run: curl https://api.example.com
        retry: 3
        retry_delay: 5  # seconds
```

## Best Practices

### 1. Use Descriptive Names

```yaml
name: "Production Environment Security Scan"
description: "Comprehensive security assessment including port scanning, vulnerability detection, and configuration review"
```

### 2. Document Inputs

```yaml
inputs:
  target:
    description: "Target hostname or IP address (e.g., example.com or 192.168.1.1)"
    required: true
  
  scan_type:
    description: "Scan type: quick, standard, or comprehensive"
    required: false
    default: "standard"
```

### 3. Validate Inputs

```yaml
jobs:
  validate:
    steps:
      - name: Check target format
        run: |
          if [[ ! "${{ inputs.target }}" =~ ^[a-zA-Z0-9.-]+$ ]]; then
            echo "Invalid target format"
            exit 1
          fi
```

### 4. Use Meaningful Job Names

```yaml
jobs:
  network_reconnaissance:
    # Clear what this job does
    
  vulnerability_assessment:
    # Clear purpose
    
  post_exploitation:
    # Clear phase
```

### 5. Organize Complex Workflows

Break large workflows into smaller, reusable workflows:

```yaml
# main_workflow.yml
jobs:
  reconnaissance:
    workflow: ./recon_workflow.yml
  
  exploitation:
    needs: [reconnaissance]
    workflow: ./exploit_workflow.yml
```

## Examples

### Simple Scan Workflow

```yaml
name: Simple Port Scan

inputs:
  target:
    description: Target host
    required: true

jobs:
  scan:
    steps:
      - name: TCP SYN scan
        run: nmap -sS ${{ inputs.target }}
      
      - name: Service detection
        run: nmap -sV ${{ inputs.target }}
```

### Complex Assessment Workflow

```yaml
name: Comprehensive Security Assessment

inputs:
  target:
    description: Target network or host
    required: true
  
  depth:
    description: Assessment depth (1-5)
    required: false
    default: "3"

secrets:
  SHODAN_KEY:
    description: Shodan API key
    required: false

hooks:
  on_start:
    script: echo "Starting assessment of ${{ inputs.target }}"
    language: shell
  
  on_success:
    script: python notify_team.py --status success
    language: shell

jobs:
  passive_recon:
    steps:
      - name: OSINT gathering
        run: python osint.py --target ${{ inputs.target }}
      
      - name: Shodan lookup
        run: |
          if [ -n "${{ secrets.SHODAN_KEY }}" ]; then
            shodan host ${{ inputs.target }}
          fi
  
  active_scan:
    needs: [passive_recon]
    steps:
      - name: Port scan
        run: nmap -sS -sV -p- ${{ inputs.target }}
      
      - name: Vulnerability scan
        run: nmap --script vuln ${{ inputs.target }}
  
  analysis:
    needs: [active_scan]
    steps:
      - name: Analyze results
        run: python analyze.py --input ${{ ctx.output_path }}/scan.xml
      
      - name: Generate report
        run: python report.py --output ${{ ctx.output_path }}/report.pdf
```

## See Also

- [Jobs & Steps](jobs-steps.md) - Detailed job and step configuration
- [Hooks System](hooks.md) - Lifecycle hooks
- [Templates](templates.md) - Template syntax and functions
- [Secrets & Inputs](secrets-inputs.md) - Managing secrets and inputs
