# Basic Concepts

Understanding OFX core concepts helps you build powerful workflows efficiently.

## Workflow

A **workflow** is the top-level container that defines a complete automation process.

### Structure

```yaml
name: workflow-name
description: Workflow description

inputs:
  # Input parameters
  
secrets:
  # Required secrets

jobs:
  # Job definitions
  
hooks:
  # Lifecycle hooks
```

### Key Properties

- **name** - Unique identifier (required)
- **description** - Human-readable description
- **inputs** - User-provided parameters
- **secrets** - Sensitive configuration
- **jobs** - Execution units
- **hooks** - Lifecycle callbacks

## Job

A **job** is an independent unit of work within a workflow.

### Characteristics

- Jobs run **sequentially** by default
- Can have **dependencies** (run after other jobs)
- Contain **steps** that execute in order
- Can define their own **hooks** and **environment**

### Example

```yaml
jobs:
  recon:
    name: Reconnaissance
    steps:
      - name: Scan ports
        run: nmap -p- ${{ inputs.target }}
  
  exploit:
    name: Exploitation
    needs: [recon]  # Runs after recon
    steps:
      - name: Launch exploit
        run: python exploit.py
```

## Step

A **step** is the smallest unit of execution within a job.

### Types of Steps

1. **Shell Command** (default)
```yaml
- name: Run command
  run: echo "Hello"
```

2. **Python Script**
```yaml
- name: Python code
  script:
  script: |
    print("Hello from Python")
```

3. **Bash Script**
```yaml
- name: Bash script
  language: bash
  script: |
    #!/bin/bash
    echo "Hello from Bash"
```

### Step Properties

- **name** - Step description
- **run** - Shell command (for shell steps)
- **script** - Code content (for script steps)
- **language** - Script language (python, bash, etc.)
- **timeout** - Maximum execution time
- **retry** - Retry configuration
- **continue_on_error** - Don't fail job on error

## Inputs

**Inputs** are parameters passed to workflows at runtime.

### Definition

```yaml
inputs:
  target:
    description: Target host or IP
    required: true
    default: "127.0.0.1"
  
  ports:
    description: Ports to scan
    required: false
    default: "80,443"
```

### Usage

**In workflow:**
```yaml
steps:
  - run: nmap -p ${{ inputs.ports }} ${{ inputs.target }}
```

**From CLI:**
```bash
ofx flow run scan --input target=example.com --input ports=22,80,443
```

### Input Properties

- **description** - Help text
- **required** - Must be provided
- **default** - Fallback value
- **type** - Data type (string, number, boolean)

## Secrets

**Secrets** are encrypted sensitive data (API keys, passwords, tokens).

### Definition

```yaml
secrets:
  api_key:
    description: API authentication key
    required: true
  
  password:
    description: Admin password
    required: false
```

### Usage

**Store secret:**
```bash
ofx secret set API_KEY
# Enter value when prompted
```

**In workflow:**
```yaml
steps:
  - run: curl -H "Authorization: Bearer ${{ secrets.api_key }}"
```

### Secret Properties

- Stored in **encrypted file** (~/.config/ofx/secrets.enc)
- **Never** logged or displayed
- Automatically loaded from secret store
- Can be provided via environment variables

## Hooks

**Hooks** are callbacks that execute at specific lifecycle events.

### Hook Types

1. **Status Hooks**
```yaml
hooks:
  on_start:
    - name: Starting message
      run: echo "Starting..."
  
  on_success:
    - name: Success message
      run: echo "Success!"
  
  on_failure:
    - name: Failure message
      run: echo "Failed!"
```

2. **Lifecycle Hooks**
```yaml
hooks:
  before_jobs:
    - name: Setup
      run: echo "Before jobs"
  
  after_jobs:
    - name: Teardown
      run: echo "After jobs"
```

3. **Command Hooks**
```yaml
hooks:
  before_command:
    - name: Pre-command
      run: echo "Before each command"
  
  after_command:
    - name: Post-command
      run: echo "After each command"
```

### Hook Scopes

Hooks can be defined at:

1. **Workflow level** - Affect entire workflow
2. **Job level** - Affect specific job
3. **Step level** - Affect specific step

### Hook Propagation

Hooks **propagate** from parent to child:

```
Workflow hooks
    ↓
Job hooks (inherit + add)
    ↓
Step hooks (inherit + add)
```

Example:
```yaml
hooks:
  on_start:
    - name: Workflow start
      run: echo "Workflow start"  # Runs once

jobs:
  job1:
    name: First Job
    hooks:
      on_start:
        - name: Job start
          run: echo "Job1 start"  # Runs at job start
    steps:
      - name: Step 1
        run: echo "Doing work"
```

See [Hooks Guide](../guide/hooks.md) for more details.

## Templates

**Templates** enable dynamic configuration using Jinja2 syntax.

### Template Syntax

```yaml
${{ expression }}
```

### Available Variables

1. **inputs** - User inputs
```yaml
${{ inputs.target }}
```

2. **secrets** - Secret values
```yaml
${{ secrets.api_key }}
```

3. **ctx** - Context variables
```yaml
${{ ctx.workflow.name }}
${{ ctx.job.name }}
${{ ctx.step.name }}
```

### Built-in Functions

**Tool Installation:**
```yaml
- run: ${{ uv_install('requests') }}
- run: ${{ pip_install('numpy') }}
- run: ${{ go_install('github.com/projectdiscovery/subfinder') }}
- run: ${{ npm_install('wappalyzer') }}
```

**Path Operations:**
```yaml
- run: ${{ output_path('results.txt') }}
- run: ${{ workflow_path() }}
```

### Template Examples

**Conditional execution:**
```yaml
steps:
  - name: Debug mode
    run: |
      {% if inputs.debug %}
      echo "Debug enabled"
      {% endif %}
```

**Loops:**
```yaml
steps:
  - name: Scan multiple targets
    run: |
      {% for target in inputs.targets.split(',') %}
      nmap {{ target }}
      {% endfor %}
```

See [Templates Guide](../guide/templates.md) for more details.

## Template Resolution

Templates are resolved **before execution** in this order:

1. **Workflow level** - Inputs, secrets loaded
2. **Job level** - Job context available
3. **Step level** - Full context available

**Example:**

```yaml
inputs:
  target: "example.com"

jobs:
  scan:
    envs:
      TARGET: ${{ inputs.target }}  # Resolved to "example.com"
    steps:
      - name: Scan
        run: nmap $TARGET  # Uses resolved env var
```

## Dependencies

Jobs can depend on other jobs using `needs`:

### Simple Dependency

```yaml
name: Sequential Jobs
jobs:
  job1:
    name: First Job
    steps:
      - name: Execute first task
        run: echo "First"
  
  job2:
    name: Second Job
    needs: [job1]  # Waits for job1
    steps:
      - name: Execute second task
        run: echo "Second"
```

### Multiple Dependencies

```yaml
name: Parallel with Convergence
jobs:
  recon:
    name: Reconnaissance
    steps:
      - name: Run recon
        run: echo "Recon"
  
  scan:
    name: Port Scan
    steps:
      - name: Run scan
        run: echo "Scan"
  
  analyze:
    name: Analysis
    needs: [recon, scan]  # Waits for both
    steps:
      - name: Analyze results
        run: echo "Analyze"
```

### Execution Flow

```
recon ─┐
       ├─→ analyze
scan ──┘
```

Jobs `recon` and `scan` run in parallel (if possible), then `analyze` runs.

## Environment Variables

Define environment variables at different levels:

### Workflow Level

```yaml
name: Environment Variables Demo
envs:
  GLOBAL_VAR: "value"

jobs:
  job1:
    name: Use Global Env
    steps:
      - name: Print global variable
        run: echo $GLOBAL_VAR  # Available
```

### Job Level

```yaml
jobs:
  job1:
    envs:
      JOB_VAR: "value"
    steps:
      - run: echo $JOB_VAR  # Available
```

### Step Level

```yaml
steps:
  - name: With env
    envs:
      STEP_VAR: "value"
    run: echo $STEP_VAR
```

## Error Handling

Control error behavior at different levels:

### Continue on Error

```yaml
jobs:
  resilient:
    continue_on_error: true  # Job continues even if step fails
    steps:
      - run: false  # Fails but job continues
      - run: echo "Still runs"
```

### Retry Configuration

```yaml
steps:
  - name: Flaky command
    retry:
      max_attempts: 3
      delay: 5  # seconds
    run: curl https://api.example.com
```

### Timeout

```yaml
steps:
  - name: Long task
    timeout: 300  # 5 minutes
    run: long-running-command
```

## Output Management

Control where outputs are saved:

### Output Directory

```yaml
# Set at workflow level
output_dir: "./results"

jobs:
  scan:
    steps:
      - run: nmap -oN output.txt ${{ inputs.target }}
        # Saves to ./results/output.txt
```

### Custom Output Path

```bash
# From CLI
ofx flow run scan --output /tmp/scan-results
```

### Accessing Outputs

```yaml
steps:
  - name: Save results
    run: echo "Results" > ${{ output_path('data.txt') }}
  
  - name: Read results
    run: cat ${{ output_path('data.txt') }}
```

## Context Variables

Access runtime information via `ctx`:

### Workflow Context

```yaml
${{ ctx.workflow.name }}        # Workflow name
${{ ctx.workflow.description }} # Description
```

### Job Context

```yaml
${{ ctx.job.name }}             # Current job name
${{ ctx.job.id }}               # Job ID
```

### Step Context

```yaml
${{ ctx.step.name }}            # Current step name
${{ ctx.step.index }}           # Step number
```

### System Context

```yaml
${{ ctx.system.os }}            # Operating system
${{ ctx.system.arch }}          # Architecture
${{ ctx.system.user }}          # Current user
```

## Best Practices

### 1. Use Descriptive Names

**Good:**
```yaml
name: comprehensive-web-app-security-scan
jobs:
  subdomain-enumeration:
    steps:
      - name: Run subfinder for subdomain discovery
```

**Bad:**
```yaml
name: scan
jobs:
  job1:
    steps:
      - name: step1
```

### 2. Validate Inputs

```yaml
inputs:
  target:
    description: Target domain (e.g., example.com)
    required: true
  
  timeout:
    description: Scan timeout in seconds
    default: 300
```

### 3. Use Hooks for Logging

```yaml
hooks:
  on_start:
    - run: echo "=== Scan started at $(date) ==="
  on_success:
    - run: echo "=== Scan completed at $(date) ==="
  on_failure:
    - run: echo "=== Scan failed at $(date) ===" >&2
```

### 4. Organize with Dependencies

```yaml
jobs:
  setup:
    steps:
      - run: mkdir -p results
  
  scan:
    needs: [setup]
    steps:
      - run: nmap -oN results/nmap.txt target
  
  cleanup:
    needs: [scan]
    steps:
      - run: tar -czf results.tar.gz results/
```

### 5. Handle Errors Gracefully

```yaml
steps:
  - name: Optional step
    continue_on_error: true
    run: experimental-tool
  
  - name: Critical step
    retry:
      max_attempts: 3
    run: important-command
```

## Next Steps

- [Workflows](../guide/workflows.md) - Comprehensive workflow guide
- [Jobs & Steps](../guide/jobs-steps.md) - Job and step configuration
- [Hooks](../guide/hooks.md) - Hook system deep dive
- [Templates](../guide/templates.md) - Template syntax and functions
- [API Overview](../api/overview.md) - Red teaming APIs
