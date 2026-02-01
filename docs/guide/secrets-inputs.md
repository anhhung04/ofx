# Secrets & Inputs

How to declare, pass, and use runtime parameters and sensitive values in OFX workflows.

---
## Inputs

```yaml
inputs:
  target: { required: true }
  ports: { default: "80,443" }
```

- Provide at run time: `ofx flow run myflow --input target=example.com --input ports=22,443`
- From Python: `RunContext(inputs={"target": "example.com"})`
- Use in templates: `{{ inputs.target }}`

---
## Secrets

```yaml
secrets:
  API_KEY: { required: true }
```

- Store once: `ofx secret set API_KEY=...` (stored, masked)
- Provide per run: `--secret API_KEY=...`
- Use in templates: `{{ secrets.API_KEY }}`

---
## Quick Validation Pattern

```yaml
- name: Validate target
  script: |
    import re, sys
    t = '{{ inputs.target }}'
    sys.exit(0 if re.match(r'^[A-Za-z0-9.-]+$', t) else 1)
```

---
## Best Practices

- Never hardcode secrets; declare them in `secrets`.
- Give clear names and defaults where sensible.
- Validate early; fail fast.
- Secrets are masked in logs; avoid printing them directly.

---
## Examples

### Input Example

```yaml
name: Comprehensive Scan

inputs:
  target:
    description: "Target hostname or IP address to scan"
    required: true
  ports:
    default: "80,443"
  output_format:
    default: "xml"

jobs:
  scan:
    steps:
      - name: Run scan
        run: |
          nmap {{ inputs.target }} \
            -p {{ inputs.ports }} \
            -T3 \
            -o{{ inputs.output_format }} {{ ctx.output_path }}/scan.{{ inputs.output_format }}
```

### Secrets Example

```yaml
name: Multi-Service Integration

secrets:
  SHODAN_API_KEY: { required: false }
  CENSYS_API_ID: { required: false }
  CENSYS_API_SECRET: { required: false }

inputs:
  target: { required: true }

jobs:
  passive_recon:
    steps:
      - name: Query Shodan
        script: |
          import requests
          api_key = '{{ secrets.SHODAN_API_KEY }}'
          if not api_key:
            print("Shodan key not provided, skipping")
          else:
            r = requests.get(
              f'https://api.shodan.io/shodan/host/{{ inputs.target }}',
              params={'key': api_key}
            )
            print(r.json())

      - name: Query Censys
        script: |
          import requests
          from requests.auth import HTTPBasicAuth
          api_id = '{{ secrets.CENSYS_API_ID }}'
          api_secret = '{{ secrets.CENSYS_API_SECRET }}'
          if not api_id or not api_secret:
            print("Censys credentials not provided, skipping")
          else:
            r = requests.get(
              'https://search.censys.io/api/v2/hosts/search',
              auth=HTTPBasicAuth(api_id, api_secret),
              params={'q': '{{ inputs.target }}'}
            )
            print(r.json())
```

---
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
            port = int('{{ inputs.port }}')
            if port < 1 or port > 65535:
              raise ValueError
          except:
            print("Port must be 1-65535")
            sys.exit(1)
```

---
## See Also

- [Workflows](workflows.md) — Workflow configuration
- [Templates](templates.md) — Using inputs and secrets in templates
- [CLI Commands](../cli/commands.md) — Command line usage
