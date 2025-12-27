# Offensive Flow Executor (OFX)

**A workflow execution framework for red teaming operations.**

Automate complex attack chains with YAML workflows, lifecycle hooks, and built-in APIs for exploitation, reconnaissance, and post-exploitation.

## Key Features

- **YAML Workflows**: Define multi-step operations with job dependencies and parallel execution
- **Lifecycle Hooks**: Execute custom code at any workflow stage (start, success, failure, etc.)
- **Red Teaming APIs**: Pre-built classes for common tasks - reduce scripting by 80%
- **Template Engine**: Dynamic configuration using Jinja2
- **Async Execution**: Run jobs in parallel for faster operations

## Red Teaming APIs

Pre-built APIs to eliminate boilerplate code:

**Reconnaissance**
- Search engines (Fofa, Shodan, ZoomEye)
- OOB testing (CEye, Interactsh)
- Network scanning (ports, services, subdomains)
- HTTP server for payload hosting

**Exploitation**
- Binary analysis (PIE, NX, Canary detection)
- Shellcode generation and encoding
- Remote connections and process execution
- ROP gadget building

**Post-Exploitation**
- File operations and data transfer
- Credential management
- Encoding/hashing utilities

**Example:**

```python
from ofx.api import Fofa, PortScanner, PHTTPServer

# Find targets
fofa = Fofa(user="email", token="token")
targets = fofa.search('app="Apache"', pages=2)

# Scan services
scanner = PortScanner()
results = scanner.scan(targets[0]['ip'], ports=[80, 443, 8080])

# Host payload
server = PHTTPServer(bind_ip='0.0.0.0', bind_port=8080)
server.start(daemon=True)
```

See [API Documentation](docs/api/overview.md) for complete reference.

## Lifecycle Hooks

Execute custom code at any workflow stage:

**Available Hooks:** `on_start`, `on_success`, `on_failure`, `on_error`, `on_end`, `on_line`, `before_run`, `after_run`

**Hook Propagation:** Step → Job → Workflow (only when explicitly defined)

```yaml
name: Example Workflow

hooks:
  on_start:
    run: echo "Starting workflow"
    language: shell
  
  on_failure:
    run: |
      import requests
      requests.post("https://alerts.com/webhook", 
                   json={"status": "failed", "workflow": "{{ workflow.name }}"})
    language: python

jobs:
  test:
    steps:
      - name: Run Tests
        run: pytest
        hooks:
          on_line:
            run: print("Test output:", line)
            language: python
```

**How it works:**
- Hooks defined at step level execute first, then propagate to job, then workflow
- If a step has no hooks, job-level hooks run
- If job has no hooks, only workflow-level hooks run
- Prevents duplicate executions while enabling hierarchical composition

See [Hooks Guide](docs/guide/hooks.md) for advanced patterns.

## Installation

```bash
pip install -e .
```

## Quick Start

### 1. Create a Workflow

Create `recon.yml`:

```yaml
name: Web Reconnaissance

jobs:
  discover:
    steps:
      - name: Port Scan
        run: |
          from ofx.api.network import PortScanner
          scanner = PortScanner()
          results = scanner.scan("{{ inputs.target }}", ports=[80, 443, 8080])
          print(f"open_ports={[r['port'] for r in results if r['status'] == 'open']}")
        language: python
        outputs:
          ports: "{{ step.open_ports }}"
      
      - name: Grab Banners
        run: |
          from ofx.api.network import ServiceGrabber
          grabber = ServiceGrabber()
          for port in {{ steps.0.outputs.ports }}:
              info = grabber.grab("{{ inputs.target }}", port)
              print(f"Port {port}: {info.get('banner', 'No banner')}")
        language: python

hooks:
  on_success:
    run: echo "Recon completed successfully"
    language: shell
```

### 2. Run the Workflow

```bash
# Basic execution
ofx flow run recon.yml --input target=example.com

# With secrets
ofx flow run recon.yml --input target=example.com --secret API_KEY=xxx
```

### 3. Use as Python Module

```python
import asyncio
from ofx.runner import WorkflowRunner, RunContext
from ofx.runner.loaders import WorkflowLoader

async def main():
    workflow = WorkflowLoader.find_flow("recon")
    runner = WorkflowRunner(
        workflow,
        ctx=RunContext(inputs={"target": "example.com"})
    )
    result = await runner.run()
    print(f"Status: {result.status}")

asyncio.run(main())
```

## How It Works

**Architecture:**
```
WorkflowRunner
  ├── JobRunner (parallel/sequential execution)
  │     └── StepRunner (commands, scripts, Python code)
  ├── Hook System (lifecycle event injection)
  └── Template Engine (Jinja2 variable resolution)
```

**Execution Flow:**
1. Load workflow YAML
2. Resolve templates with inputs/secrets
3. Execute jobs (respecting dependencies)
4. Run steps within each job
5. Trigger hooks at each lifecycle stage
6. Collect outputs and results

**Core Components:**
- `runner/`: Workflow, job, and step execution
- `models/`: Workflow, job, step data models  
- `api/`: Red teaming API modules
- `commands/`: CLI commands
- `utils/`: Helpers for logging, secrets, caching

See [Architecture Guide](docs/advanced/architecture.md) for details.

## Documentation

- [Quick Start Guide](docs/getting-started/quickstart.md)
- [Workflow Syntax](docs/guide/workflows.md)
- [Hook System](docs/guide/hooks.md)
- [Template Variables](docs/guide/templates.md)
- [API Reference](docs/api/overview.md)
- [Extending Data Modules](docs/guide/extending-data-modules.md)

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test
pytest tests/test_flowrun.py

# With coverage
pytest --cov=ofx tests/
```

## Contributing

Contributions welcome! Please use semantic commit messages:

- `feat:` - New features
- `fix:` - Bug fixes
- `breaking:` - Breaking changes
- `docs:`, `test:`, `refactor:`, `chore:` - Other changes

**Workflow:**
1. Fork and create a feature branch
2. Make changes and add tests
3. Run `pytest tests/`
4. Submit PR with semantic title

Version bumps are automatic based on PR titles.

## License

See LICENSE file for details.
