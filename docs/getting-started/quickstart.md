# Quick Start

5-minute path: create a workflow, validate, run, add inputs/secrets.

## 1) Initialize

```bash
ofx project init quickstart-demo
cd ~/.local/share/ofx/projects/quickstart-demo
```

## 2) Minimal Workflow

`~/.config/ofx/workflows/hello.yml`
```yaml
name: hello-world
jobs:
  greet:
    steps:
      - run: echo "Hello from OFX"
  info:
    needs: [greet]
    steps:
      - run: date
      - run: pwd
```

Validate & run:
```bash
ofx flow validate hello-world
ofx flow run hello-world
```

## 3) Inputs

```yaml
name: port-scanner
inputs:
  target: { required: true }
  ports: { default: "80,443" }
jobs:
  scan:
    steps:
      - run: ${{ uv_install('nmap-python') }}
      - run: nmap -p ${{ inputs.ports }} ${{ inputs.target }}
```
Run: `ofx flow run port-scanner --input target=scanme.nmap.org --input ports=22,80,443`

## 4) Secrets

```bash
ofx secret set API_KEY
```
```yaml
name: api-test
secrets:
  API_KEY: { required: true }
jobs:
  call:
    steps:
      - run: curl -H "Authorization: Bearer ${{ secrets.API_KEY }}" https://api.example.com/data
```
Run: `ofx flow run api-test`

## 5) Multi-job

```yaml
name: basic-recon
inputs: { domain: { required: true } }
jobs:
  subdomain-enum:
    steps:
      - run: subfinder -d ${{ inputs.domain }} -o subdomains.txt
  port-scan:
    needs: [subdomain-enum]
    steps:
      - run: nmap -iL subdomains.txt -p 80,443 -oN nmap-results.txt
  analyze:
    needs: [subdomain-enum, port-scan]
    steps:
      - run: cat nmap-results.txt
```

## 6) Hooks (quick)

```yaml
hooks:
  on_start:
    - run: echo "Starting ${{ inputs.target }}"
  on_success:
    - run: echo "Done"
```

## Common Commands

```bash
ofx flow validate <workflow>
ofx flow run <workflow>
ofx x run <workflow>          # alias
ofx secret list
ofx docs serve
ofx doctor
```

Next: [concepts](concepts.md) → [workflows](../guide/workflows.md) → [CLI](../cli/commands.md).
