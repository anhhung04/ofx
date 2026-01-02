# Templates

OFX uses Jinja2 templates with `${{ }}` syntax for dynamic value substitution in workflows, jobs, and steps.

## Basic Syntax

```yaml
# Template syntax
${{ variable_name }}

# Example
run: echo "Target is ${{ inputs.target }}"
```

## Available Variables

### Inputs

Access workflow input parameters:

```yaml
inputs:
  target: example.com
  ports: "80,443"

steps:
  - run: nmap -p ${{ inputs.ports }} ${{ inputs.target }}
```

### Secrets

Access sensitive configuration values:

```yaml
steps:
  - run: curl -H "Authorization: Bearer ${{ secrets.API_KEY }}" https://api.example.com
```

### Context Variables

Access execution context:

| Variable | Description | Example |
|----------|-------------|---------|
| `${{ ctx.run_id }}` | Unique run identifier | `20231225_143022_abc123` |
| `${{ ctx.output_path }}` | Output directory path | `/tmp/ofx/output/run_id` |
| `${{ ctx.workflow_dir }}` | Workflow file directory | `/path/to/workflows` |

```yaml
steps:
  - run: cp results.txt ${{ ctx.output_path }}/results_${{ ctx.run_id }}.txt
```

## Built-in Functions

### Tool Installation

#### uv_install
Install Python packages with uv:

```yaml
steps:
  - run: ${{ uv_install('requests beautifulsoup4') }}
  - script: |
      import requests
      response = requests.get('https://example.com')
```

#### pip_install
Install Python packages with pip:

```yaml
steps:
  - run: ${{ pip_install('scapy nmap') }}
```

#### go_install
Install Go packages:

```yaml
steps:
  - run: ${{ go_install('github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest') }}
  - run: ${{ tools_bin_dir }}/nuclei -version
```

#### cargo_install
Install Rust packages:

```yaml
steps:
  - run: ${{ cargo_install('ripgrep') }}
  - run: ${{ tools_bin_dir }}/rg --version
```

#### npm_install
Install Node.js packages globally:

```yaml
steps:
  - run: ${{ npm_install('http-server') }}
  - run: ${{ tools_bin_dir }}/http-server
```

### Tool Directories

#### tools_dir
Base directory for installed tools:

```yaml
steps:
  - run: ls -la ${{ tools_dir }}
  # Output: /home/user/.ofx/tools
```

#### tools_bin_dir
Binary directory for installed tools:

```yaml
steps:
  - run: export PATH=${{ tools_bin_dir }}:$PATH
  - run: nuclei -version
```

### Custom Tool Installation

#### install_tool
Install tool with custom command:

```yaml
steps:
  - run: ${{ install_tool('tool_name', 'wget https://example.com/tool && chmod +x tool') }}
```

## Template Examples

### Dynamic Port Scanning

```yaml
inputs:
  target:
    required: true
  ports:
    default: "80,443,8080"
  scan_type:
    default: "syn"

steps:
  - name: Scan ports
    run: nmap -p${{ inputs.ports }} -s${{ inputs.scan_type }} ${{ inputs.target }}
  
  - name: Save results
    run: mv scan.xml ${{ ctx.output_path }}/scan_${{ ctx.run_id }}.xml
```

### Conditional Execution

```yaml
inputs:
  mode:
    default: "standard"

steps:
  - name: Quick scan
    run: nmap -F ${{ inputs.target }}
    # Use shell conditionals for complex logic
    
  - name: Full scan
    script: |
      if [ "${{ inputs.mode }}" = "aggressive" ]; then
        nmap -p- -T4 ${{ inputs.target }}
      else
        nmap -T3 ${{ inputs.target }}
      fi
    language: shell
```

### API Integration

```yaml
secrets:
  SHODAN_API_KEY:
    required: true

steps:
  - name: Query Shodan
    script: |
      import requests
      
      api_key = '${{ secrets.SHODAN_API_KEY }}'
      target = '${{ inputs.target }}'
      
      response = requests.get(
        f'https://api.shodan.io/shodan/host/{target}',
        params={'key': api_key}
      )
      
      print(response.json())
```

### Tool Installation and Usage

```yaml
steps:
  - name: Install scanning tools
    run: |
      ${{ go_install('github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest') }}
      ${{ go_install('github.com/projectdiscovery/httpx/cmd/httpx@latest') }}
      ${{ uv_install('python-nmap') }}
  
  - name: Run subdomain enumeration
    run: ${{ tools_bin_dir }}/subfinder -d ${{ inputs.target }} -o ${{ ctx.output_path }}/subdomains.txt
  
  - name: Probe HTTP services
    run: cat ${{ ctx.output_path }}/subdomains.txt | ${{ tools_bin_dir }}/httpx -o ${{ ctx.output_path }}/http.txt
```

### File Path Management

```yaml
steps:
  - name: Create directory structure
    run: |
      mkdir -p ${{ ctx.output_path }}/scans
      mkdir -p ${{ ctx.output_path }}/reports
      mkdir -p ${{ ctx.output_path }}/logs
  
  - name: Run scan
    run: nmap ${{ inputs.target }} -oX ${{ ctx.output_path }}/scans/nmap_${{ ctx.run_id }}.xml
  
  - name: Generate report
    script: |
      import xml.etree.ElementTree as ET
      import json
      
      tree = ET.parse('${{ ctx.output_path }}/scans/nmap_${{ ctx.run_id }}.xml')
      # Process XML...
      
      with open('${{ ctx.output_path }}/reports/report_${{ ctx.run_id }}.json', 'w') as f:
        json.dump(report_data, f)
```

### Environment Configuration

```yaml
envs:
  LOG_LEVEL: INFO
  TIMEOUT: "300"

steps:
  - name: Configure environment
    run: |
      export LOG_LEVEL=${{ env.LOG_LEVEL }}
      export TIMEOUT=${{ env.TIMEOUT }}
      python scanner.py --target ${{ inputs.target }}
```

## Advanced Templates

### Nested Templates

```yaml
steps:
  - name: Complex command
    run: |
      ${{ uv_install('requests') }}
      python -c "
      import requests
      r = requests.get('https://${{ inputs.target }}')
      with open('${{ ctx.output_path }}/response_${{ ctx.run_id }}.txt', 'w') as f:
        f.write(r.text)
      "
```

### Template in Python Scripts

```yaml
steps:
  - name: Python with templates
    script: |
      import os
      import json
      from pathlib import Path
      
      # Access template variables
      target = '${{ inputs.target }}'
      output_path = Path('${{ ctx.output_path }}')
      run_id = '${{ ctx.run_id }}'
      
      # Create structured output
      result_file = output_path / f'scan_{run_id}.json'
      
      data = {
        'target': target,
        'timestamp': run_id,
        'results': perform_scan(target)
      }
      
      with open(result_file, 'w') as f:
        json.dump(data, f, indent=2)
```

### Template in Shell Scripts

```yaml
steps:
  - name: Bash with templates
    script: |
      #!/bin/bash
      
      TARGET="${{ inputs.target }}"
      OUTPUT_DIR="${{ ctx.output_path }}"
      RUN_ID="${{ ctx.run_id }}"
      
      echo "Scanning $TARGET..."
      
      # Run scan
      nmap -sV "$TARGET" -oN "$OUTPUT_DIR/scan_$RUN_ID.txt"
      
      # Process results
      grep "open" "$OUTPUT_DIR/scan_$RUN_ID.txt" > "$OUTPUT_DIR/open_ports_$RUN_ID.txt"
    language: bash
```

## Template Best Practices

### 1. Quote Template Values in Shell

```yaml
# Good - Quoted for safety
- run: nmap -p "${{ inputs.ports }}" "${{ inputs.target }}"

# Bad - May break with spaces or special chars
- run: nmap -p ${{ inputs.ports }} ${{ inputs.target }}
```

### 2. Validate Template Values

```yaml
steps:
  - name: Validate input
    script: |
      import re
      
      target = '${{ inputs.target }}'
      
      # Validate format
      if not re.match(r'^[a-zA-Z0-9.-]+$', target):
        print(f"Invalid target format: {target}")
        sys.exit(1)
```

### 3. Use Meaningful Names

```yaml
inputs:
  # Good - Clear purpose
  target_hostname:
    description: Target server hostname
  
  scan_timeout_seconds:
    description: Maximum scan duration in seconds
  
  # Bad - Unclear
  t:
    description: target
  
  timeout:
    description: timeout
```

### 4. Provide Defaults

```yaml
inputs:
  target:
    required: true
    # No default - must be provided
  
  ports:
    required: false
    default: "80,443,8080"
    # Default provided
  
  scan_speed:
    required: false
    default: "normal"
    # Default for optional parameter
```

### 5. Document Template Usage

```yaml
# Document what each template variable represents
inputs:
  api_endpoint:
    description: "API endpoint URL (e.g., https://api.example.com)"
    required: true
  
  rate_limit:
    description: "Maximum requests per second (1-100)"
    default: "10"

steps:
  - name: Call API with rate limiting
    # Template variables:
    # - api_endpoint: Base URL for API calls
    # - rate_limit: Throttle requests
    run: python api_client.py --url "${{ inputs.api_endpoint }}" --rate ${{ inputs.rate_limit }}
```

## Troubleshooting Templates

### Template Not Resolving

```yaml
# Check for typos
${{ inputs.traget }}  # Wrong: traget
${{ inputs.target }}  # Correct: target

# Check for undefined variables
${{ inputs.nonexistent }}  # Error: nonexistent not defined

# Verify input is declared
inputs:
  target:  # Must be declared
    required: true
```

### Shell Escaping Issues

```yaml
# Problem: Special characters
- run: echo ${{ inputs.message }}  # Breaks if message contains quotes

# Solution: Proper quoting
- run: echo "${{ inputs.message }}"

# Alternative: Use script block
- script: |
    message="${{ inputs.message }}"
    echo "$message"
  language: bash
```

### Path Issues

```yaml
# Problem: Relative paths
- run: cp file.txt output/  # Where is output/?

# Solution: Use ctx.output_path
- run: cp file.txt ${{ ctx.output_path }}/

# Problem: Path with spaces
- run: cd /path with spaces/  # Breaks

# Solution: Quote the path
- run: cd "${{ ctx.output_path }}/"
```

## Template Reference

### Complete Variable List

```yaml
# Inputs
${{ inputs.variable_name }}

# Secrets
${{ secrets.secret_name }}

# Context
${{ ctx.run_id }}           # Unique run identifier
${{ ctx.output_path }}      # Output directory path
${{ ctx.workflow_dir }}     # Workflow directory

# Environment
${{ env.VARIABLE_NAME }}    # Environment variables

# Tool Functions
${{ uv_install('package') }}           # Install Python package with uv
${{ pip_install('package') }}          # Install Python package with pip
${{ go_install('package@version') }}   # Install Go package
${{ cargo_install('package') }}        # Install Rust package
${{ npm_install('package') }}          # Install Node package

# Tool Paths
${{ tools_dir }}            # Tool installation directory
${{ tools_bin_dir }}        # Tool binary directory
```

## See Also

- [Workflows](workflows.md) - Workflow configuration
- [Jobs & Steps](jobs-steps.md) - Using templates in jobs and steps
- [Secrets & Inputs](secrets-inputs.md) - Managing inputs and secrets
