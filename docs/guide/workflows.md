# Workflows

Top-level container: define inputs, secrets, jobs, hooks.

## Skeleton

```yaml
name: my-workflow
inputs:
  target: { required: true }
secrets:
  API_KEY: { required: false }
jobs:
  scan:
    steps:
      - run: nmap -sV ${{ inputs.target }}
  analyze:
    needs: [scan]
    steps:
      - run: python analyze.py
```

## Key fields

- `name`, optional `description`.
- `inputs`/`secrets`: declare and reference with `${{ inputs.* }}` / `${{ secrets.* }}`.
- `envs`: workflow-wide env vars.
- `jobs`: required map; see [jobs & steps](jobs-steps.md).

## Run

```bash
ofx flow validate my-workflow
ofx flow run my-workflow --input target=example.com --secret API_KEY=xxx
```

## Workflow Sources

OFX can load workflows from multiple sources:

### Local Files

```bash
# Current directory
ofx flow run my-workflow.yml

# Absolute path
ofx flow run /path/to/workflow.yml

# From workflow directories
ofx flow run my-workflow  # Searches ~/.local/share/ofx/workflows
```

### Git Repositories

```bash
# Clone and run main workflow
ofx flow run https://github.com/user/repo

# Specific workflow in repo
ofx flow run https://github.com/user/repo/workflows/scan.yml
```

### HTTP/HTTPS URLs

```bash
# Direct URL to workflow file
ofx flow run https://example.com/workflows/security-scan.yml
```

### S3 Buckets

```bash
# S3 URI with full path
ofx flow run s3://my-workflows-bucket/prod/main.yml

# Automatic extension detection
ofx flow run s3://my-workflows-bucket/workflows/scan

# With AWS credentials from environment or ~/.aws/credentials
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
ofx flow run s3://my-bucket/workflow.yml
```

**S3 Requirements:**
- boto3 installed (included by default in OFX)
- AWS credentials configured via environment variables, ~/.aws/credentials, or IAM role
- Read permissions on the S3 bucket and object

**Supported extensions:** `.yml`, `.yaml`

## Dependencies

- `needs` controls order; missing `needs` = parallel.
```yaml
jobs:
  a: { steps: [{ run: echo a }] }
  b:
    needs: [a]
    steps: [{ run: echo b }]
  c:
    needs: [a]
    steps: [{ run: echo c }]
```

## Hooks (workflow-level)

```yaml
hooks:
  on_start:
    - run: echo "start"
  on_success:
    - run: echo "ok"
```

## Python entry (minimal)

```python
import yaml, asyncio
from pathlib import Path
from ofx.runner import WorkflowRunner, RunContext
from ofx.models.workflow import Workflow

async def main():
    data = yaml.safe_load(Path("workflow.yml").read_text())
    wf = Workflow(**data)
    res = await WorkflowRunner(wf, RunContext()).run()
    print(res.status)

asyncio.run(main())
```
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
      - name: Port scan
        run: nmap ${{ inputs.target }}
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
