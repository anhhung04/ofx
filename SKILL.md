---
name: ofx-workflow-generator
description: Guide for agents generating OFX (Offensive Flow Executor) workflow YAML files. Covers syntax, schema validation, step types, job dependencies, matrix/fleet strategies, cloud execution, remote targets (SSH/WinRM), API modules, templating, sessions, and collections. Use when asked to create, edit, or review OFX workflow files.
allowed-tools: read_file, grep_search, run_in_terminal, file_search, list_dir
---

# OFX Workflow Generator

## Quick Decision Tree

| User asks for... | What to do |
|---|---|
| New workflow from scratch | `ofx flow init <name>` then edit the generated file |
| Modify existing workflow | Read the file, apply edits, validate |
| Validate a workflow | Run `ofx flow validate <file>` |
| Use a built-in API module | Check `src/ofx/api/<category>/` for available modules |
| Run on remote machines | Use `remote` step type with SSH/WinRM connection |
| Run on cloud VPS | Add `cloud:` to job + `provider:` to step, configure profile |
| Distribute across fleet | Use `strategy.fleet` with count + distribution mode |
| Schema-aware editing | Ensure `# yaml-language-server: $schema=...` comment at top |

## Before Writing Any Workflow

1. **Check existing examples** — `src/ofx/data/workflows/` contains 60+ reference workflows.
2. **Generate schema** — `ofx flow schema schema` writes `~/.ofx/workflow_schema.json` for IDE autocompletion.
3. **Init from template** — `ofx flow init <name>` creates a scaffolded YAML with the schema comment.

## Workflow Structure Rules

### Top-Level

```yaml
# yaml-language-server: $schema=~/.ofx/workflow_schema.json
name: workflow-name          # required, kebab-case
description: >               # optional but recommended
  Detailed description.
tags: [redteam, recon]       # optional, for collection filtering
dispatch:                    # optional, defines user inputs
  inputs:
    target:
      required: true
      type: string
      description: Target host
      alias: t               # optional short flag
env:                         # optional, globals available to all jobs
  THREADS: "10"
jobs:                        # required
  job-name:
    ...
```

### Jobs

- Each job runs in parallel unless `needs` is specified.
- `needs` accepts a single job name or a list.
- Topological sort auto-resolves execution order.
- Job names must be valid YAML keys (no spaces, no dots).

```yaml
jobs:
  setup:
    steps: [...]
  scan:
    needs: setup
    steps: [...]
  report:
    needs: [setup, scan]
    steps: [...]
```

### Step Types (exactly one per step)

| Type | Key | Use Case |
|---|---|---|
| Shell | `run:` | Any shell command |
| Python inline | `script:` | Multi-line Python logic |
| Python file | `script_file:` | Path to `.py` file |
| Subworkflow | `uses:` | Reference another workflow YAML |
| Remote (SSH) | `remote:` | Run on remote host via SSH |
| Remote (WinRM) | `remote:` | Run on remote host via WinRM |

### Step Common Options

```yaml
- name: Step name
  run: echo hello
  shell: /bin/bash          # default: /bin/bash
  working-directory: /tmp   # optional
  timeout: 5                # minutes, 0 = no timeout
  retry: 3                  # retry count
  retry-delay: 10           # seconds between retries
  continue-on-error: true   # don't fail job on error
  if: success()             # success() | failure() | always()
  log-command: true         # log the command itself
  log-output: true          # log stdout/stderr
```

## Remote Execution (SSH / WinRM)

When a step targets a remote machine, use the `remote:` key with a connection object:

```yaml
jobs:
  deploy:
    steps:
      - name: Run on remote Linux
        remote:
          host: '{{ inputs.target }}'
          port: 22
          username: '{{ inputs.user }}'
          password: '{{ inputs.password }}'   # or use key
          key-file: '{{ inputs.ssh_key }}'
          command: |
            whoami
            hostname
            uname -a && cat /etc/os-release

      - name: Run on remote Windows
        remote:
          host: '{{ inputs.target }}'
          port: 5986
          username: '{{ inputs.user }}'
          password: '{{ inputs.password }}'
          protocol: winrm
          use-ssl: true
          command: |
            whoami
            systeminfo | findstr /B /C:"OS Name"
```

### Remote connection fields

| Field | SSH | WinRM | Notes |
|---|---|---|---|
| `host` | ✅ | ✅ | Required |
| `port` | ✅ | ✅ | SSH default 22, WinRM default 5986 |
| `username` | ✅ | ✅ | Required |
| `password` | ✅ | ✅ | Optional if using key |
| `key-file` | ✅ | ❌ | Path to SSH private key |
| `protocol` | ✅ | ✅ | `ssh` or `winrm` |
| `use-ssl` | ❌ | ✅ | Default: true |
| `command` | ✅ | ✅ | Multi-line shell commands |

## Cloud Execution

Run jobs on provisioned or pre-existing VPS instances.

### Cloud Profile Setup

```bash
ofx cloud profile create do-nyc \
  --provider digitalocean \
  --region nyc3 \
  --size s-2vcpu-4gb \
  --image ubuntu-24-04-x64 \
  --ssh-key ~/.ssh/id_rsa

ofx cloud profile create aws-prod \
  --provider aws \
  --region us-east-1 \
  --instance-type t3.medium \
  --ami ami-0c7217cd432ea2da7 \
  --ssh-key ~/.ssh/aws_key
```

### Cloud Job Configuration

```yaml
jobs:
  scan:
    cloud: do-nyc              # references a cloud profile
    cloud-timeout: 30          # VPS teardown timeout in minutes
    steps:
      - run: nmap -sV {{ inputs.target }}
```

### Fleet Distribution (Multi-VPS)

```yaml
jobs:
  mass-scan:
    cloud: do-nyc
    strategy:
      matrix:
        port: [80, 443, 8080]
      fleet:
        count: 5                       # number of VPS instances
        input: '{{ inputs.targets }}'  # IPs, CIDRs, hostnames, or file path
        distribution: chunk            # chunk | round-robin | subnet | line
        expand_cidrs: true             # expand CIDR ranges to individual IPs
        exclude: ['10.0.0.1']          # skip specific targets
    steps:
      - run: |
          cat $FLEET_INPUT_FILE | xargs -I{} nmap -p{{ matrix.port }} {}
```

`$FLEET_INPUT_FILE` is auto-uploaded to each VPS with its chunk of targets.

## Matrix Strategy

Run a job across variable combinations:

```yaml
jobs:
  fuzz:
    strategy:
      matrix:
        target: [api.example.com, admin.example.com]
        method: [GET, POST, PUT]
      max_parallel: 4
      fail_fast: false
      exclude:
        - target: admin.example.com
          method: GET
      include:
        - target: internal.example.com
          method: PATCH
          extra_header: 'X-Custom: 1'
    steps:
      - run: 'curl -X {{ matrix.method }} https://{{ matrix.target }}'
```

Matrix variables are available as `{{ matrix.<key> }}` in templates.

## Templating (Jinja2)

### Template Context Sources

| Source | Syntax | Scope |
|---|---|---|
| Inputs | `{{ inputs.target }}` | Workflow-wide |
| Env vars | `{{ env.THREADS }}` | Workflow-wide |
| Matrix | `{{ matrix.target }}` | Job-level |
| Job outputs | `{{ jobs['scan'].outputs.hosts }}` | Cross-job |
| Step outputs | `{{ steps['probe'].outputs.data }}` | Within job |
| API modules | `{{ recon.portscan(...) }}` | Anywhere |

### Outputs and Data Passing

```yaml
jobs:
  scan:
    outputs:
      hosts: '{{ steps["nmap-scan"].outputs.hosts }}'
    steps:
      - name: nmap-scan
        run: nmap -sL {{ inputs.range }} -oG -
        # Use add_outputs() in script steps to set outputs:
      - name: parse
        script: |
          hosts = []
          # ... parse logic ...
          add_outputs(hosts='\n'.join(hosts), count=len(hosts))

  report:
    needs: scan
    steps:
      - run: echo "Found {{ jobs['scan'].outputs.count }} hosts"
```

### API Module Access in Scripts

Python `script:` steps can import `ofx.api` modules directly. They're auto-bundled for cloud execution:

```yaml
- name: DNS enumeration
  script: |
    from ofx.api.dns import resolve, bruteforce
    records = resolve("example.com", record_type="A")
    subs = bruteforce("example.com", wordlist="/usr/share/wordlists/subdomains.txt")
    add_outputs(a_records=records, subdomains=subs)
```

## Built-in API Module Categories

| Category | Path | Key Capabilities |
|---|---|---|
| `ad` | `ofx.api.ad` | AD enumeration, Kerberos, DCSync, LDAP queries, BloodHound |
| `bundle` | `ofx.api.bundle` | Payload bundling, self-extracting archives |
| `creds` | `ofx.api.creds` | Credential extraction, KeePass, token manipulation |
| `dns` | `ofx.api.dns` | Resolution, bruteforce, zone transfer, reverse lookup |
| `evasion` | `ofx.api.evasion` | AMSI bypass, obfuscation, packer detection |
| `exfil` | `ofx.api.exfil` | DNS/HTTP/ICMP exfiltration, encoding/decoding |
| `exploitation` | `ofx.api.exploitation` | Shellcode, webshells, exploit connectors |
| `file` | `ofx.api.file` | File upload/download, hash, pack/unpack |
| `http` | `ofx.api.http` | HTTP client, proxy, auth, sessions |
| `httpserver` | `ofx.api.httpserver` | Payload delivery, exfil listener, file server |
| `network` | `ofx.api.network` | Portscan, proxy, tunnel, pivot |
| `oob` | `ofx.api.oob` | Out-of-band (DNS/HTTP) interaction testing |
| `opsec` | `ofx.api.opsec` | Log cleanup, timestamp manipulation, artifact removal |
| `packers` | `ofx.api.packers` | UPX, PE packers, binary manipulation |
| `payloads` | `ofx.api.payloads` | Payload generation, encoding, staging |
| `post` | `ofx.api.post` | Post-exploitation runners, persistence, pivoting |
| `privesc` | `ofx.api.privesc` | Linux/Windows privilege escalation enumeration |
| `recon` | `ofx.api.recon` | OSINT, port scanning, web fingerprinting, subdomain enum |
| `search` | `ofx.api.search` | Shodan, Censys, Google dorking |
| `service` | `ofx.api.service` | Service interaction (SMB, RDP, FTP, etc.) |
| `strings` | `ofx.api.strings` | Encoding, decoding, hashing, transformation |

## Validation & Syntax Checking

```bash
# Validate a workflow YAML (schema + semantic checks)
ofx flow validate workflow.yml

# Generate schema for IDE autocompletion
ofx flow schema schema

# Init a new workflow from template
ofx flow init my-workflow

# Dry-run: show what would execute without running
ofx flow run workflow.yml --dry-run

# Run with verbose output for debugging
ofx flow run workflow.yml -v
```

## Sessions (Detached Execution)

For long-running or fire-and-forget workflows:

```bash
ofx session submit workflow.yml --cloud do-nyc
ofx session list
ofx session status <id>
ofx session logs <id> --tail 100
ofx session fetch <id> --passphrase secret
ofx session cancel <id>
ofx session destroy <id>
ofx session clean --older-than 7d
```

Results are AES-256-CBC encrypted at rest.

## Secrets Management

```bash
# Store a secret
ofx secret set TARGET_PASSWORD --value "s3cret"

# Use in workflows
# {{ secrets.TARGET_PASSWORD }}
```

## Collections

```bash
# Install a collection
ofx collection install ./my-collection

# List installed
ofx collection list

# Run a collection workflow
ofx collection run my-collection workflow-name --input target=10.0.0.1
```

## Common Patterns

### Recon → Exploit → Post-Exploit Pipeline

```yaml
jobs:
  recon:
    outputs:
      live_hosts: ...
    steps: [...]
  exploit:
    needs: recon
    outputs:
      sessions: ...
    steps: [...]
  post:
    needs: exploit
    steps: [...]
```

### Multi-Target Parallel Scan

```yaml
jobs:
  scan:
    strategy:
      matrix:
        target: '{{ inputs.targets | fromjson }}'
      max_parallel: 10
    steps:
      - run: nmap -sV -p- {{ matrix.target }}
```

### Conditional Cleanup

```yaml
jobs:
  cleanup:
    needs: exploit
    steps:
      - name: Clean artifacts
        if: success()
        remote:
          host: '{{ inputs.target }}'
          username: '{{ inputs.user }}'
          key-file: '{{ inputs.ssh_key }}'
          command: rm -rf /tmp/ofx_* /dev/shm/ofx_*
```

## Pitfalls to Avoid

- **Missing schema comment** — Always include `# yaml-language-server: $schema=~/.ofx/workflow_schema.json` at line 1.
- **Job name collisions** — Job names must be unique within a workflow.
- **Circular dependencies** — `needs` cycles cause validation errors.
- **Unquoted template expressions** — Wrap `{{ }}` in quotes in YAML: `'{{ inputs.target }}'`.
- **Step type ambiguity** — Each step must have exactly one of: `run`, `script`, `script_file`, `uses`, `remote`.
- **Matrix variable clashes** — Don't name matrix variables the same as `dispatch.inputs` keys.
- **Cloud without profile** — `cloud:` references must match an existing `ofx cloud profile` name.
- **Fleet without cloud** — `strategy.fleet` requires `cloud:` on the job.
