# CLI Commands

Complete reference for all OFX command-line interface commands.

## Workflow Commands

- **[flow run](run.md)** - Execute workflows
- **[flow validate](validate.md)** - Validate workflow syntax
- **[flow visualize](visualize.md)** - Visualize workflow dependencies
- **[flow tools](tools.md)** - Manage workflow tools
- **[flow update](update.md)** - Update workflows

## Project Commands

- **[project init](init.md)** - Initialize new OFX project
- **[project sync](sync.md)** - Sync project to remote storage
- **[project list](project.md)** - List and manage projects

## Secret Management

- **[secret manage](secret.md)** - Manage secrets and credentials

## Asset Management

- **[asset](asset.md)** - Manage asset collections and workflows

## Utility Commands

- **[docs](docs-serve.md)** - Display API documentation and data directories
- **[doctor](doctor.md)** - Diagnose system dependencies
- **[dump](dump.md)** - Dump and analyze data structures

## Quick Start

### Viewing Data Directories

```bash
# Show where to place custom workflows and data
ofx docs
```

### Finding API Documentation

```bash
# List all available API modules
ofx docs --list

# View specific module documentation
ofx docs --module webshell
```

### Working with Workflows

```bash
# Run a workflow
ofx flow run workflow-name

# Validate workflow syntax
ofx flow validate workflow-name

# Visualize workflow dependencies
ofx flow visualize workflow-name
```

### Managing Secrets

```bash
# Add a secret
ofx secret add api_key

# List all secrets
ofx secret list
```

## Command Index

| Command | Description |
|---------|-------------|
| `ofx flow run` | Execute a workflow |
| `ofx flow validate` | Validate workflow syntax |
| `ofx flow visualize` | Visualize workflow dependency graph |
| `ofx flow tools` | Install and manage workflow tools |
| `ofx flow update` | Update workflow definitions |
| `ofx project init` | Initialize new project |
| `ofx project sync` | Sync project to storage |
| `ofx secret manage` | Manage secrets |
| `ofx asset` | Manage asset collections |
| `ofx docs` | Display API documentation and data directories |
| `ofx docs --list` | List all available API modules |
| `ofx docs --module <name>` | View specific module documentation |
| `ofx doctor` | Check system dependencies |
| `ofx dump` | Dump data structures |
