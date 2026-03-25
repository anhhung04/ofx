# Quickstart Examples

Real-world workflow examples from simple to advanced. Save any example as a `.yml` file and run with `ofx flow run <file>`.

---

## 1. Hello World

The simplest possible workflow — one job, one step.

```yaml
name: hello-world
jobs:
  greet:
    steps:
      - name: Say hello
        run: echo "Hello from OFX!"
```

```bash
ofx flow run hello-world.yml
```

---

## 2. Parameterized Scan

Accept inputs from the command line and use them in steps.

```yaml
name: quick-scan
description: Run a fast port scan against a target

dispatch:
  inputs:
    target:
      type: string
      required: true
      description: IP or hostname to scan
    ports:
      type: string
      default: "80,443,22,8080"
      description: Ports to scan

jobs:
  scan:
    steps:
      - name: Port scan
        run: nmap -sT -p {{ inputs.ports }} {{ inputs.target }}
```

```bash
ofx flow run quick-scan.yml --input target=10.10.10.1 --input ports=1-1000
```

---

## 3. Multi-Job Pipeline with Dependencies

Chain jobs together — `enumerate` runs first, then `analyze` uses its output.

```yaml
name: recon-pipeline
description: Subdomain discovery → HTTP probing

dispatch:
  inputs:
    domain:
      type: string
      required: true

jobs:
  enumerate:
    steps:
      - name: Find subdomains
        run: subfinder -d {{ inputs.domain }} -silent -o subs.txt
    outputs:
      subs_file: subs.txt

  probe:
    needs: [enumerate]
    steps:
      - name: HTTP probe
        run: httpx -l {{ jobs['enumerate'].outputs.subs_file }} -silent
```

```bash
ofx flow run recon-pipeline.yml --input domain=example.com
```

---

## 4. Matrix Strategy (Parallel Expansion)

Run the same job across multiple targets or configurations in parallel.

```yaml
name: multi-scan
description: Scan multiple targets simultaneously

jobs:
  scan:
    strategy:
      matrix:
        target: ["10.10.10.1", "10.10.10.2", "10.10.10.3"]
      max_parallel: 3
    steps:
      - name: Scan host
        run: nmap -sV {{ matrix.target }} -oN scan_{{ matrix.target }}.txt
```

```bash
ofx flow run multi-scan.yml
```

---

## 5. Using Secrets

Store sensitive values securely and reference them in workflows.

```bash
# Set a secret
ofx secret set API_KEY
```

```yaml
name: api-check
description: Call an API with authentication

jobs:
  check:
    steps:
      - name: Authenticated request
        run: |
          curl -s -H "Authorization: Bearer {{ secrets.API_KEY }}" \
            https://api.example.com/status
```

---

## 6. Task Steps (Built-in Tool Wrappers)

Use pre-built task wrappers for common security tools — they parse output into structured data.

```yaml
name: task-example
description: Port scan with structured output

dispatch:
  inputs:
    target:
      type: string
      required: true

jobs:
  discover:
    steps:
      - name: Port scan
        task: nmap
        with:
          target: "{{ inputs.target }}"
          opts: "-sV --top-ports 100"
        timeout: 10
    outputs:
      open_ports: "{{ steps['Port scan'].typed_outputs | ports | join(',') }}"
```

Available tasks: `nmap`, `nuclei`, `httpx`, `subfinder`, `ffuf`, `feroxbuster`, `katana`, and [many more](../../guide/tasks.md).

---

## 7. Reusable Workflows

Reference other workflows as steps with `uses:`.

```yaml
name: full-recon
description: Chain multiple workflows together

dispatch:
  inputs:
    domain:
      type: string
      required: true

jobs:
  subdomains:
    steps:
      - name: Run subdomain recon
        uses: recon/subdomain-recon
        with:
          target: "{{ inputs.domain }}"

  web-audit:
    needs: [subdomains]
    steps:
      - name: Run web audit
        uses: web/web-full-audit
        with:
          target: "{{ inputs.domain }}"
```

---

## 8. Project Integration

Bind a workflow to a project for organized output and scoped context.

```bash
# Create a project
ofx project init pentest-acme

# Run workflow within project context
ofx flow run recon/subdomain-recon --input target=acme.com --project pentest-acme

# All outputs saved to ~/.ofx/projects/pentest-acme/
```

---

## Common Patterns

### Conditional Steps

```yaml
- name: Exploit only if vulnerable
  run: python3 exploit.py {{ inputs.target }}
  if: "{{ 'VULNERABLE' in steps['Check vuln'].stdout }}"
```

### Retry on Failure

```yaml
- name: Flaky network request
  run: curl -s https://unstable-api.example.com
  retry: 3
  retry-delay: 5
```

### Tool Installation

```yaml
tools:
  subfinder:
    install: "{{ go_install('github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest') }}"
    check: subfinder -version
```

---

## What's Next

- Browse 120+ [built-in workflows](../../cli/commands/list.md): `ofx flow list --builtin`
- [Workflow guide](../../guide/workflows.md) — full YAML reference
- [Templates](../../guide/templates.md) — Jinja2 expressions and helpers
- [Cloud runners](../../guide/cloud-runners.md) — run on remote VPS