# Secrets & Inputs

Learn how to manage sensitive configuration and runtime parameters in OFX workflows.

## Inputs

Inputs are parameters passed to workflows at runtime. They make workflows reusable and configurable.

### Defining Inputs

```yaml
name: Configurable Scan

inputs:
  target:
    description: Target hostname or IP address
    required: true
  
  ports:
    description: Comma-separated list of ports to scan
    required: false
    default: "80,443,8080"
  
  scan_type:
    description: Type of scan (quick|standard|comprehensive)
    required: false
    default: "standard"
```

### Input Properties

#### description
Human-readable description of the input:

```yaml
inputs:
  target:
    description: "Target server (hostname or IP). Example: example.com or 192.168.1.1"
```

#### required
Whether the input must be provided:

```yaml
inputs:
  target:
    required: true   # Must be provided
  
  ports:
    required: false  # Optional
```

#### default
Default value if not provided:

```yaml
inputs:
  ports:
    required: false
    default: "80,443,8080,8443"
  
  timeout:
    required: false
    default: "300"
```

### Providing Inputs

#### Command Line

```bash
# Single input
ofx flow run workflow.yml --input target=example.com

# Multiple inputs
ofx flow run workflow.yml \
  --input target=192.168.1.1 \
  --input ports="22,80,443" \
  --input scan_type=comprehensive
```

#### Python API

```python
from ofx.runner import WorkflowRunner, RunContext
from ofx.models.workflow import Workflow

# Load workflow
workflow = Workflow.from_file("workflow.yml")

# Create context with inputs
ctx = RunContext(
    inputs={
        "target": "192.168.1.1",
        "ports": "22,80,443",
        "scan_type": "comprehensive"
    }
)

# Run workflow
runner = WorkflowRunner(workflow, ctx)
await runner.run()
```

### Using Inputs

Access inputs using `${{ inputs.name }}`:

```yaml
steps:
  - name: Scan target
    run: nmap -p ${{ inputs.ports }} ${{ inputs.target }}
  
  - name: Generate report
    script: |
      print(f"Scanning {ctx.inputs['target']}")
      print(f"Ports: {ctx.inputs['ports']}")
      print(f"Type: {ctx.inputs['scan_type']}")
    script:
```

### Input Validation

Validate inputs before execution:

```yaml
jobs:
  validate:
    steps:
      - name: Validate target
        script: |
          import re
          import sys
          
          target = '${{ inputs.target }}'
          
          # Check format
          if not re.match(r'^[a-zA-Z0-9.-]+$', target):
            print(f"Invalid target format: {target}")
            sys.exit(1)
          
          print(f"✓ Valid target: {target}")
        script:
      
      - name: Validate ports
        script: |
          import sys
          
          ports = '${{ inputs.ports }}'
          
          # Check port range
          for port in ports.split(','):
            try:
              p = int(port.strip())
              if p < 1 or p > 65535:
                raise ValueError
            except:
              print(f"Invalid port: {port}")
              sys.exit(1)
          
          print(f"✓ Valid ports: {ports}")
        language: python
```

## Secrets

Secrets are sensitive values that should not be hardcoded or logged. OFX provides secure secret management.

### Defining Secrets

```yaml
name: API Integration

secrets:
  API_KEY:
    description: API key for external service
    required: true
  
  API_SECRET:
    description: API secret for authentication
    required: false
  
  DATABASE_URL:
    description: Database connection string
    required: true
```

### Secret Properties

Same as inputs, but stored securely:

```yaml
secrets:
  SHODAN_API_KEY:
    description: "Shodan API key from https://account.shodan.io/"
    required: true
```

### Managing Secrets

#### Command Line

```bash
# Provide at runtime
ofx flow run workflow.yml --secret API_KEY=your_key_here

# Multiple secrets
ofx flow run workflow.yml \
  --secret API_KEY=key123 \
  --secret API_SECRET=secret456
```

#### Secret Store

Store secrets persistently:

```bash
# Set secret
ofx secret set API_KEY=your_key_here

# List secrets
ofx secret list

# Delete secret
ofx secret delete API_KEY
```

Then use in workflows without providing at runtime:

```bash
# Secrets automatically loaded from store
ofx flow run workflow.yml --input target=example.com
```

#### Environment Variables

Load secrets from environment:

```bash
export API_KEY=your_key_here
export API_SECRET=your_secret_here

# OFX automatically loads from environment
ofx flow run workflow.yml
```

#### Python API

```python
ctx = RunContext(
    inputs={"target": "example.com"},
    secrets={
        "API_KEY": "your_key_here",
        "API_SECRET": "your_secret_here"
    }
)
```

### Using Secrets

Access secrets using `${{ secrets.name }}`:

```yaml
steps:
  - name: Call API
    run: curl -H "Authorization: Bearer ${{ secrets.API_KEY }}" https://api.example.com
  
  - name: Authenticate
    script: |
      import requests
      
      api_key = '${{ secrets.API_KEY }}'
      response = requests.post(
        'https://api.example.com/auth',
        headers={'X-API-Key': api_key}
      )
      
      print(response.json())
    script:
```

### Secret Security

Secrets are:
- ✅ Not logged in output
- ✅ Not visible in process listings
- ✅ Encrypted at rest (in secret store)
- ✅ Masked in error messages

```yaml
steps:
  - name: Use secret safely
    script: |
      # Secret value is masked in logs
      api_key = '${{ secrets.API_KEY }}'
      
      # This will NOT print the actual key
      print(f"Using API key: {api_key}")  # Masked output
      
      # Use secret normally
      authenticate(api_key)
    language: python
```

## Best Practices

### 1. Never Hardcode Secrets

```yaml
# Bad - Secret in workflow file
steps:
  - run: curl -H "Authorization: Bearer abc123def456" https://api.example.com

# Good - Secret as parameter
secrets:
  API_KEY:
    required: true

steps:
  - run: curl -H "Authorization: Bearer ${{ secrets.API_KEY }}" https://api.example.com
```

### 2. Use Meaningful Names

```yaml
inputs:
  # Good - Clear purpose
  target_hostname:
    description: "Primary target server hostname"
  
  scan_timeout_seconds:
    description: "Maximum scan duration in seconds"
  
  # Bad - Unclear
  t:
    description: "target"
  
  x:
    description: "timeout"
```

### 3. Provide Defaults When Appropriate

```yaml
inputs:
  # Required, no default
  target:
    required: true
    description: "Must be provided by user"
  
  # Optional with sensible default
  timeout:
    required: false
    default: "300"
    description: "5 minute default timeout"
```

### 4. Document Expected Formats

```yaml
inputs:
  target:
    description: |
      Target specification:
      - Hostname: example.com
      - IPv4: 192.168.1.1
      - IPv6: 2001:db8::1
      - CIDR: 192.168.1.0/24
    required: true
  
  ports:
    description: |
      Port specification:
      - Single: 80
      - Range: 1-1000
      - List: 80,443,8080
      - Mixed: 22,80-443,8080
    default: "80,443"
```

### 5. Validate Early

```yaml
jobs:
  validate_inputs:
    steps:
      - name: Validate all inputs
        script: |
          import sys
          
          # Validate target
          if not validate_target('${{ inputs.target }}'):
            sys.exit(1)
          
          # Validate ports
          if not validate_ports('${{ inputs.ports }}'):
            sys.exit(1)
          
          print("✓ All inputs valid")
        script:
  
  main_work:
    needs: [validate_inputs]
    steps:
      - run: nmap ${{ inputs.target }}
```

### 6. Use Secret Store for Persistent Secrets

```bash
# One-time setup
ofx secret set SHODAN_API_KEY=your_key_here
ofx secret set CENSYS_API_ID=your_id_here
ofx secret set CENSYS_API_SECRET=your_secret_here

# Workflows automatically use stored secrets
ofx flow run recon.yml --input target=example.com
```

### 7. Separate Secrets by Environment

```bash
# Development secrets
ofx secret set API_KEY=dev_key_here --env dev

# Production secrets
ofx secret set API_KEY=prod_key_here --env prod

# Run with specific environment
ofx flow run workflow.yml --env prod
```

## Examples

### Complete Input Example

```yaml
name: Comprehensive Scan

inputs:
  target:
    description: "Target hostname or IP address to scan"
    required: true
  
  ports:
    description: "Ports to scan (e.g., 80,443 or 1-1000)"
    required: false
    default: "1-1000"
  
  scan_speed:
    description: "Scan speed: slow (T2), normal (T3), fast (T4), aggressive (T5)"
    required: false
    default: "normal"
  
  output_format:
    description: "Output format: text, xml, json"
    required: false
    default: "xml"

jobs:
  scan:
    steps:
      - name: Configure scan
        script: |
          speed_map = {
            'slow': '-T2',
            'normal': '-T3',
            'fast': '-T4',
            'aggressive': '-T5'
          }
          
          speed_flag = speed_map.get('${{ inputs.scan_speed }}', '-T3')
          format_flag = '-o${{ inputs.output_format }}'.upper()
          
          print(f"Speed: {speed_flag}")
          print(f"Format: {format_flag}")
        language: python
      
      - name: Run scan
        run: |
          nmap ${{ inputs.target }} \
            -p ${{ inputs.ports }} \
            -T3 \
            -o${{ inputs.output_format }} ${{ ctx.output_path }}/scan.${{ inputs.output_format }}
```

### Complete Secret Example

```yaml
name: Multi-Service Integration

secrets:
  SHODAN_API_KEY:
    description: "Shodan API key"
    required: false
  
  CENSYS_API_ID:
    description: "Censys API ID"
    required: false
  
  CENSYS_API_SECRET:
    description: "Censys API secret"
    required: false
  
  SLACK_WEBHOOK:
    description: "Slack webhook URL for notifications"
    required: false

jobs:
  passive_recon:
    steps:
      - name: Query Shodan
        script: |
          import requests
          
          api_key = '${{ secrets.SHODAN_API_KEY }}'
          if not api_key:
            print("Shodan API key not provided, skipping")
            sys.exit(0)
          
          target = '${{ inputs.target }}'
          response = requests.get(
            f'https://api.shodan.io/shodan/host/{target}',
            params={'key': api_key}
          )
          
          print(response.json())
        language: python
      
      - name: Query Censys
        script: |
          import requests
          from requests.auth import HTTPBasicAuth
          
          api_id = '${{ secrets.CENSYS_API_ID }}'
          api_secret = '${{ secrets.CENSYS_API_SECRET }}'
          
          if not api_id or not api_secret:
            print("Censys credentials not provided, skipping")
            sys.exit(0)
          
          response = requests.get(
            'https://search.censys.io/api/v2/hosts/search',
            auth=HTTPBasicAuth(api_id, api_secret),
            params={'q': '${{ inputs.target }}'}
          )
          
          print(response.json())
        language: python
  
  notify:
    needs: [passive_recon]
    hooks:
      on_success:
        script: |
          import requests
          import json
          
          webhook = '${{ secrets.SLACK_WEBHOOK }}'
          if webhook:
            requests.post(webhook, json={
              'text': f'✅ Recon completed for ${{ inputs.target }}'
            })
        language: python
```

## Troubleshooting

### Input Not Found

```
Error: Required input 'target' not provided
```

**Solution:**
```bash
ofx flow run workflow.yml --input target=example.com
```

### Secret Not Found

```
Error: Required secret 'API_KEY' not provided
```

**Solutions:**
```bash
# Option 1: Provide at runtime
ofx flow run workflow.yml --secret API_KEY=your_key

# Option 2: Store in secret store
ofx secret set API_KEY=your_key
ofx flow run workflow.yml

# Option 3: Use environment variable
export API_KEY=your_key
ofx flow run workflow.yml
```

### Invalid Input Format

```
Error: Invalid port number: abc
```

**Solution:** Add validation:
```yaml
jobs:
  validate:
    steps:
      - script: |
          try:
            port = int('${{ inputs.port }}')
            if port < 1 or port > 65535:
              raise ValueError
          except:
            print("Port must be 1-65535")
            sys.exit(1)
        language: python
```

## See Also

- [Workflows](workflows.md) - Workflow configuration
- [Templates](templates.md) - Using inputs and secrets in templates
- [CLI Commands](../cli/commands.md) - Command line usage
