# Quick Start

Get started with OFX workflows in under 5 minutes.

## Your First Workflow

### 1. Initialize a Project

```bash
# Create a new project
ofx project init quickstart-demo

# Navigate to project directory
cd ~/.local/share/ofx/projects/quickstart-demo
```

### 2. Create a Simple Workflow

Create a file named `hello.yml` in `~/.config/ofx/workflows/`:

```yaml
name: hello-world
description: My first OFX workflow

jobs:
  greet:
    name: Say Hello
    steps:
      - name: Print greeting
        run: echo "Hello from OFX!"
      
      - name: Show date
        run: date
      
      - name: List files
        run: ls -lah

  analyze:
    name: System Info
    needs: [greet]
    steps:
      - name: Python version
        run: python3 --version
      
      - name: Current directory
        run: pwd
```

### 3. Validate the Workflow

```bash
ofx flow validate hello-world
```

Expected output:
```
✓ Workflow 'hello-world' is valid
```

### 4. Run the Workflow

```bash
ofx flow run hello-world
```

You'll see:
- Job execution progress
- Real-time step output
- Success indicators

## Adding Inputs

Create `scan.yml` with inputs:

```yaml
name: port-scanner
description: Simple port scanner

inputs:
  target:
    description: Target IP or hostname
    required: true
  
  ports:
    description: Ports to scan
    default: "80,443,8080"

jobs:
  scan:
    name: Port Scan
    steps:
      - name: Install nmap
        run: ${{ uv_install('nmap-python') }}
      
      - name: Scan ports
        run: |
          echo "Scanning ${{ inputs.target }}"
          echo "Ports: ${{ inputs.ports }}"
          nmap -p ${{ inputs.ports }} ${{ inputs.target }}
```

Run with inputs:

```bash
ofx flow run port-scanner \
  --input target=scanme.nmap.org \
  --input ports=22,80,443
```

## Using Secrets

### 1. Store a Secret

```bash
ofx secret set API_KEY
# Enter value when prompted (input hidden)
```

### 2. Use in Workflow

Create `api-call.yml`:

```yaml
name: api-test
description: Test API with secret

secrets:
  api_key:
    description: API authentication key
    required: true

jobs:
  call-api:
    name: Call API
    steps:
      - name: Make request
        run: |
          curl -H "Authorization: Bearer ${{ secrets.api_key }}" \
            https://api.example.com/data
```

Run:

```bash
ofx flow run api-test
# OFX automatically loads API_KEY from secret store
```

## Using OFX APIs

Create `webshell.yml` using OFX APIs:

```yaml
name: webshell-demo
description: WebShell API demonstration

inputs:
  url:
    description: WebShell URL
    required: true
  
  param:
    description: Command parameter
    default: "cmd"

jobs:
  exploit:
    name: WebShell Exploitation
    steps:
      - name: Execute command
        script: |
          from ofx.api import webshell
          
          shell = webshell.WebShell(
              url="${{ inputs.url }}",
              param="${{ inputs.param }}"
          )
          
          # List directory
          result = shell.execute("ls -la")
          print(result)
          
          # Check user
          whoami = shell.execute("whoami")
          print(f"Current user: {whoami}")
```

Run:

```bash
ofx flow run webshell-demo \
  --input url=http://vulnerable.lab/shell.php \
  --input param=cmd
```

## Multi-Job Workflows

Create `recon.yml` with dependencies:

```yaml
name: basic-recon
description: Basic reconnaissance workflow

inputs:
  domain:
    description: Target domain
    required: true

jobs:
  subdomain-enum:
    name: Enumerate Subdomains
    steps:
      - name: Run subfinder
        run: |
          subfinder -d ${{ inputs.domain }} -o subdomains.txt
          cat subdomains.txt

  port-scan:
    name: Scan Discovered Hosts
    needs: [subdomain-enum]
    steps:
      - name: Run nmap
        run: |
          nmap -iL subdomains.txt -p 80,443,8080 -oN nmap-results.txt
  
  analyze:
    name: Analyze Results
    needs: [subdomain-enum, port-scan]
    steps:
      - name: Summary
        run: |
          echo "=== Reconnaissance Summary ==="
          echo "Subdomains found: $(wc -l < subdomains.txt)"
          echo "Nmap results:"
          cat nmap-results.txt
```

Run:

```bash
ofx flow run basic-recon --input domain=example.com
```

Jobs execute in order: subdomain-enum → port-scan → analyze

## Using Hooks

Add lifecycle hooks to `scan.yml`:

```yaml
name: scan-with-hooks
description: Workflow with hooks

inputs:
  target:
    required: true

hooks:
  on_start:
    - name: Notify start
      run: echo "🚀 Starting scan of ${{ inputs.target }}"
  
  on_success:
    - name: Notify success
      run: echo "✅ Scan completed successfully!"
  
  on_failure:
    - name: Notify failure
      run: echo "❌ Scan failed!"

jobs:
  scan:
    name: Scan Target
    hooks:
      on_start:
        - run: echo "Starting job: scan"
    steps:
      - name: Run scan
        run: nmap -sV ${{ inputs.target }}
```

Hooks execute at different lifecycle stages:
- Workflow start/end
- Job start/end
- Step start/end

## Viewing Documentation

### Web Documentation

```bash
# Start docs server
ofx docs serve

# Open browser to http://localhost:8000
```

### API Documentation

```bash
# List all API modules
ofx docs api --list

# View module details
ofx docs api --module http

# View specific function
ofx docs api --module webshell --function WebShell.execute
```

## Check System Health

```bash
# Run comprehensive health check
ofx doctor
```

Output shows:
- ✓ Installed tools
- ✗ Missing tools
- Installation suggestions

## Common Commands

```bash
# List secrets
ofx secret list

# Validate workflow
ofx flow validate <workflow-name>

# Run workflow
ofx flow run <workflow-name>

# Run with alias
ofx x run <workflow-name>

# Install workflow tools
ofx flow tools <workflow-name>

# Dump workflow schema
ofx dump schema
```

## Next Steps

Now that you understand the basics:

1. **Learn Concepts** - Read [Basic Concepts](concepts.md)
2. **Explore Workflows** - Check [Workflow Guide](../guide/workflows.md)
3. **Use APIs** - Read [API Overview](../api/overview.md)
4. **Master CLI** - See [CLI Commands](../cli/commands.md)
5. **Advanced Topics** - Review [Performance Guide](../advanced/performance.md)
