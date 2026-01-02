# Welcome to OFX

<div class="grid cards" markdown>

-   :material-lightning-bolt:{ .lg .middle } **Powerful Workflows**

    ---

    Execute complex multi-job workflows with dependencies, lifecycle hooks, and flexible execution strategies.

    [:octicons-arrow-right-24: Quick Start](getting-started/quickstart.md)

-   :material-shield-bug:{ .lg .middle } **Red Teaming APIs**

    ---

    15+ classes for exploitation, reconnaissance, and post-exploitation. Reduce scripting overhead by 80-90%.

    [:octicons-arrow-right-24: Explore APIs](api/overview.md)

-   :material-hook:{ .lg .middle } **Lifecycle Hooks**

    ---

    Inject custom logic at any point in execution with comprehensive hook system and propagation.

    [:octicons-arrow-right-24: Learn about hooks](getting-started/concepts.md#hook-propagation)

-   :material-code-braces:{ .lg .middle } **Template Support**

    ---

    Jinja2 templating for dynamic configuration with built-in helper functions.

    [:octicons-arrow-right-24: Template guide](getting-started/concepts.md#template-resolution)

</div>

## What is OFX?

**Offensive Flow Executor (OFX)** is a powerful workflow execution framework designed specifically for red teaming operations. It combines:

- **Workflow orchestration** with dependency management
- **Comprehensive hook system** for lifecycle customization
- **Red teaming APIs** that eliminate boilerplate code
- **Async execution** for efficient parallel operations
- **Template support** for dynamic configurations

## Key Features

### Workflow Orchestration

Execute multi-job workflows with dependencies and automatic execution ordering.

```yaml
name: Reconnaissance Workflow
jobs:
  discovery:
    steps:
      - run: nmap -sV ${{ inputs.target }}
      
  analysis:
    needs: [discovery]
    steps:
      - run: python analyze.py
```

### Lifecycle Hooks

Run custom code at different stages of execution:

```yaml
hooks:
  on_start:
    - run: echo "Starting..."
  on_success:
    - run: echo "Success!"
```

### Red Teaming APIs

Use built-in APIs to simplify common tasks:

```python
from ofx.api import webshell, http

# Execute commands via webshell
shell = webshell.WebShell(url="http://target/shell.php")
result = shell.execute("whoami")

# Make HTTP requests
response = http.fetch("https://api.example.com")
```

### Performance Optimized

Fast execution with async support and efficient resource management.

## Quick Example

=== "CLI"

    ```bash
    # Run a workflow
    ofx flow run ./my_workflow.yml
    
    # With inputs
    ofx flow run ./workflow.yml --input target=example.com
    
    # With secrets
    ofx flow run ./workflow.yml --secret API_KEY=xxx
    ```

=== "Python Module"

    ```python
    import asyncio
    from ofx.runner import WorkflowRunner, RunContext
    from ofx.runner.loaders import WorkflowLoader
    
    async def main():
        workflow = WorkflowLoader.find_flow("my_workflow")
        runner = WorkflowRunner(workflow, ctx=RunContext())
        result = await runner.run()
        print(f"Status: {result.status}")
    
    asyncio.run(main())
    ```

=== "Red Team API"

    ```python
    from ofx.api import PortScanner, ServiceGrabber
    
    # Port scanning
    scanner = PortScanner(target='192.168.1.1', ports='1-1000')
    open_ports = scanner.scan()
    
    # Service grabbing
    grabber = ServiceGrabber(target='192.168.1.1', port=80)
    banner = grabber.grab_banner()
    ```

## Next Steps

<div class="grid cards" markdown>

-   **New to OFX?**
    
    Start with the [Quick Start](getting-started/quickstart.md) and [Basic Concepts](getting-started/concepts.md)

-   **Build Workflows**
    
    Learn about [Workflows](guide/workflows.md), [Jobs & Steps](guide/jobs-steps.md), and [Hooks](guide/hooks.md)

-   **Use Red Team APIs**
    
    Explore [API Overview](api/overview.md) for reconnaissance, exploitation, and post-exploitation

-   **Learn More**
    
    Check [Templates](guide/templates.md), [Secrets](guide/secrets-inputs.md), and [CLI Commands](cli/commands.md)

</div>
