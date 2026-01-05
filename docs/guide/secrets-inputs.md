# Secrets & Inputs

How to declare, pass, and use runtime parameters and sensitive values.

## Inputs

```yaml
inputs:
  target: { required: true }
  ports: { default: "80,443" }
```

- Provide at run: `ofx flow run myflow --input target=example.com --input ports=22,443`.
- Python: `RunContext(inputs={"target": "example.com"})`.
- Use: `${{ inputs.target }}` inside steps.

## Secrets

```yaml
secrets:
  API_KEY: { required: true }
```

- Provide once: `ofx secret set API_KEY=...` (stored, masked), or per run `--secret API_KEY=...`, or env var.
- Use: `${{ secrets.API_KEY }}`.

## Quick validation pattern

```yaml
- name: Validate target
  script: |
    import re, sys
    t='${{ inputs.target }}'
    sys.exit(0 if re.match(r'^[A-Za-z0-9.-]+$', t) else 1)
  language: python
```

## Best practices

- Never hardcode secrets; declare in `secrets`.
- Give clear names and defaults where sensible.
- Validate early; fail fast.
- Secrets are masked in logs; avoid printing them directly.
  main_work:
    needs: [validate_inputs]
    steps:
      - name: Scan target
        run: nmap ${{ inputs.target }}
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
