# Templates

Jinja2 with `${{ ... }}` is used everywhere in workflows, jobs, and steps.

## What you can reference

- Inputs: `${{ inputs.target }}`
- Secrets: `${{ secrets.API_KEY }}` (masked)
- Context: `${{ ctx.run_id }}`, `${{ ctx.output_path }}`

## Handy helpers

- `${{ tools_dir }}` / `${{ tools_bin_dir }}`
- `${{ uv_install('requests') }}`
- `${{ go_install('module@latest') }}`
- `${{ cargo_install('ripgrep') }}`
- `${{ npm_install('http-server') }}`
- `${{ sudo }}` is set when available.

## Quick examples

```yaml
- run: echo "Target ${{ inputs.target }}"

- run: ${{ uv_install('python-nmap') }}

- run: |
    ${{ go_install('github.com/projectdiscovery/httpx/cmd/httpx@latest') }}
    ${{ tools_bin_dir }}/httpx -u https://${{ inputs.target }}

- script: |
    from pathlib import Path
    Path('${{ ctx.output_path }}').mkdir(parents=True, exist_ok=True)
    print('${{ ctx.run_id }}')
  language: python
```

## Tips

- Quote template values in shell commands: `"${{ inputs.ports }}"`.
- Keep templates simple; move heavy logic into scripts.
- Validate inputs before using them in templates.

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
