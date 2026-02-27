# Quick Start

> **Time:** 5 minutes | **Goal:** Create, validate, and run your first workflow

---

## 1️⃣ Initialize a Project

```bash
ofx project init quickstart-demo
cd ~/ofx-projects/quickstart-demo
```

---

## 2️⃣ Create Your First Workflow

Create `hello.yml` in your workflows directory:

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

**Validate and run:**

```bash
ofx flow validate hello-world
ofx flow run hello-world
```

---

## 3️⃣ Add User Inputs

Make your workflow dynamic with inputs:

```yaml
name: port-scanner
dispatch:
  inputs:
    target:
      required: true
      description: Target host to scan
    ports:
      default: "80,443"
      description: Comma-separated ports

jobs:
  scan:
    steps:
      - run: uv_install nmap-python
      - run: nmap -p {{ inputs.ports }} {{ inputs.target }}
```

**Run with inputs:**

```bash
ofx flow run port-scanner --input target=scanme.nmap.org --input ports=22,80,443
```

---

## 4️⃣ Secure Your Secrets

Store sensitive credentials securely:

```bash
ofx secret set API_KEY
# Enter your secret when prompted
```

**Use in workflow:**

```yaml
name: api-test
call:
  secrets:
    API_KEY:
      required: true

jobs:
  call:
    steps:
      - run: |
          curl -H "Authorization: Bearer {{ secrets.API_KEY }}" \
               https://api.example.com/data
```

```bash
ofx flow run api-test
```

---

## 5️⃣ Chain Multiple Jobs

Create complex workflows with job dependencies:

```yaml
name: basic-recon
dispatch:
  inputs:
    domain:
      required: true
      description: Target domain

jobs:
  subdomain-enum:
    steps:
      - run: subfinder -d {{ inputs.domain }} -o subdomains.txt

  port-scan:
    needs: [subdomain-enum]
    steps:
      - run: nmap -iL subdomains.txt -p 80,443 -oN nmap-results.txt

  analyze:
    needs: [subdomain-enum, port-scan]
    steps:
      - run: cat nmap-results.txt
```

> **💡 Tip:** Jobs run in parallel unless `needs` specifies dependencies.

---

## 6️⃣ Durable Execution (Resume)

Durable execution writes checkpoints to the output directory so you can resume
from the last completed step after a restart:

```bash
ofx flow run basic-recon --output ./runs/basic-recon --durable --resume
```

To use Redis-backed checkpoints:

```bash
ofx flow run basic-recon \
  --output ./runs/basic-recon \
  --durable \
  --durable-backend redis \
  --durable-redis-prefix ofx:durable:
```

---

## 📋 Command Reference

| Command | Description |
|---------|-------------|
| `ofx flow validate <workflow>` | Check workflow syntax |
| `ofx flow run <workflow>` | Execute workflow |
| `ofx x run <workflow>` | Shorthand for run |
| `ofx secret list` | List stored secrets |
| `ofx secret set <name>` | Add new secret |
| `ofx docs serve` | View docs locally |
| `ofx doctor` | Check installation |

---

## ➡️ Next Steps

1. **[Core Concepts](concepts.md)** — Understand the architecture
2. **[Workflows Guide](../guide/workflows.md)** — Deep dive into workflow syntax
3. **[Templates](../guide/templates.md)** — Jinja2 templating & helpers
4. **[CLI Reference](../cli/commands.md)** — Full command documentation
