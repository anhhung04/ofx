# Offensive Flow Executor (OFX)

A workflow execution framework for red teaming operations.

Automate complex attack chains with YAML workflows, lifecycle hooks, and built-in APIs for exploitation, reconnaissance, and post-exploitation.

## Key Features

- YAML Workflows: Define multi-step operations with job dependencies and parallel execution
- Lifecycle Hooks: Execute custom code at any workflow stage
- Red Teaming APIs: Pre-built classes for common tasks
- Template Engine: Dynamic configuration using Jinja2
- Async Execution: Run jobs in parallel for faster operations

## Installation

```bash
pip install -e .
```

## Quick Start

Create a workflow YAML file and run it:

```bash
ofx flow run your_workflow.yml --input target=example.com
```

See [Documentation](docs/index.md) for detailed guides, API reference, and examples.

## Contributing

Contributions welcome! Use semantic commit messages. See docs for development setup.

## License

See LICENSE file for details.
