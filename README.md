# Offensive Flow Executor (OFX)

A powerful workflow execution framework with lifecycle hooks and flexible execution strategies, optimized for red teaming operations with comprehensive exploitation, reconnaissance, and post-exploitation APIs.

## Features

- **Workflow Orchestration**: Execute complex multi-job workflows with dependencies
- **Lifecycle Hooks**: Inject custom logic at any point in the execution lifecycle (inspired by [secator](https://docs.freelabz.com/in-depth/concepts/runners))
- **Flexible Execution**: Support for commands, scripts, and nested workflows
- **Template Support**: Jinja2 templating for dynamic configuration
- **Design Patterns**: Built with Template Method, Strategy, Factory, and Composition patterns
- **Async/Await**: Full async support for efficient parallel execution
- **Red Teaming APIs**: 15+ classes for exploitation, reconnaissance, and post-exploitation with minimal boilerplate

## Red Teaming Enhancement

OFX now includes comprehensive red teaming APIs to reduce scripting overhead by 80-90%:

### Reconnaissance APIs
- **Search Engines**: Fofa, Shodan, ZoomEye for asset discovery
- **OOB Testing**: CEye, Interactsh for DNS/HTTP callback verification
- **HTTP Server**: PHTTPServer for hosting payloads with SSL support
- **PortScanner**: Fast port discovery with service detection
- **ServiceGrabber**: Banner grabbing and HTTP information gathering
- **DNSResolver**: DNS enumeration with A, MX, NS, TXT record resolution
- **SubdomainEnumerator**: Wildcard-aware subdomain discovery
- **NetworkScanner**: Live host discovery via ping sweep

### Exploitation APIs
- **RemoteTarget**: Socket connections with context manager support
- **BinaryAnalyzer**: Security property analysis (PIE, NX, Canary, RELRO)
- **PayloadBuilder**: Shellcode and ROP gadget generation
- **ProcessRunner**: Local binary execution with I/O control
- **Network Utilities**: Shell binding (TCP/Telnet), reverse shells, shellcode generation

### Post-Exploitation APIs
- **FileUtils**: File operations (read, write, copy, delete, find)
- **ProcessUtils**: Command execution and subprocess management
- **CryptoUtils**: Hashing, HMAC, Base64/Hex encoding
- **DataTransformer**: Format conversions and data manipulation
- **CredentialManager**: Secure credential storage and retrieval

### Quick Example

```python
from ofx.api import Fofa, CEye, PHTTPServer

# Asset discovery
fofa = Fofa(user="email@example.com", token="your_token")
targets = fofa.search('app="Apache"', pages=2)

# OOB callback testing
ceye = CEye(token="your_token")
payload = ceye.build_request("test_data", type='dns')
# Check if callback received
if ceye.verify_request(payload['flag'], type='dns'):
    print("Callback received!")

# Host payloads
server = PHTTPServer(bind_ip='0.0.0.0', bind_port=8080, use_https=True)
server.start(daemon=True)
```

**For detailed API documentation**, see [REDTEAMING_API.md](REDTEAMING_API.md) or start with [QUICKREF.md](QUICKREF.md) for a quick reference card.

## Hook System

OFX includes a comprehensive hook system that allows you to execute custom code at various lifecycle points:

### Hook Propagation

Hooks **conditionally propagate** from child to parent scope: **Step → Job → Workflow**

**Key behavior**: Propagation only occurs when hooks are explicitly defined at a level:

- **Step with hooks** → Step executes, then propagates to Job → then Workflow
- **Step without hooks** → Job hooks execute, then propagate to Workflow  
- **Job without hooks** → Only Workflow hooks execute

This prevents unnecessary duplicate executions while enabling hierarchical composition:
- Global logging at workflow level (always available)
- Job-specific notifications that bubble up to workflow
- Step-specific error handling that propagates through the chain

### Available Hooks

- **Lifecycle**: `before_init`, `on_init`, `on_start`, `on_iter`, `on_end`, `before_run`, `after_run`
- **Status**: `on_success`, `on_failure`, `on_error`, `on_cancel`
- **Commands**: `on_cmd`, `on_cmd_done`, `on_line`

### Quick Example

```yaml
name: My Workflow

hooks:
  on_start:
    script: "print('Workflow starting!')"
    language: python
  
  on_success:
    script: "echo 'Success!'"
    language: shell

jobs:
  build:
    steps:
      - name: Build
        run: make build
        hooks:
          on_line:
            script: "print('Output:', line)"
            language: python
```

## Installation

```bash
pip install -e .
```

## Quick Start

### Command Line

```bash
# Run a workflow
ofx flow run ./my_workflow.yml

# Run with inputs
ofx flow run ./my_workflow.yml --input key=value

# Run with secrets
ofx flow run ./my_workflow.yml --secret API_KEY=xxx
```

### As a Module

OFX can be used as a module in your Python applications:

```python
import asyncio
from pathlib import Path
from ofx.runner import WorkflowRunner, RunContext
from ofx.runner.loaders import WorkflowLoader

async def main():
    # Load workflow
    workflow = WorkflowLoader.find_flow("my_workflow")
    
    # Create runner (executor managed automatically)
    runner = WorkflowRunner(
        workflow,
        ctx=RunContext(
            inputs={"key": "value"},
            output_path=Path("./output"),
            secrets={},
            envs=os.environ.copy(),
        ),
    )
    
    # Run and get result
    result = await runner.run()
    print(f"Status: {result.status}")

asyncio.run(main())
```

#### Advanced: Shared Executor

For running multiple workflows efficiently, share a `ThreadPoolExecutor`:

```python
from concurrent.futures import ThreadPoolExecutor

async def run_multiple():
    with ThreadPoolExecutor(max_workers=4) as executor:
        runner1 = WorkflowRunner(workflow1, ctx1, executor=executor)
        runner2 = WorkflowRunner(workflow2, ctx2, executor=executor)
        
        result1 = await runner1.run()
        result2 = await runner2.run()
```

See `examples/module_usage.py` for complete examples including:
- Standalone execution (automatic lifecycle)
- Shared executor patterns
- Application-level orchestrators
- Custom executor configuration

## Architecture

The runner module is organized into focused components:

- `context.py` - Execution context and result models
- `hooks.py` - Hook system with lifecycle management
- `template.py` - Jinja2 template resolution
- `base_runner.py` - Abstract base runner with Template Method pattern
- `managers.py` - Orchestration (dependencies, scheduling, job execution)
- `loaders.py` - Workflow loading from files, URLs, git repos
- `workflow.py`, `job.py`, `step.py` - Concrete runner implementations

## Testing

```bash
pytest tests/
```