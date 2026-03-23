# CLI Commands

Complete reference for all OFX command-line interface commands.

## Workflow Commands

- **[flow init](flow-init.md)** - Scaffold a new workflow file with IDE schema support
- **[flow run](run.md)** - Execute workflows
- **[flow list](list.md)** - List available workflows from user, built-in, and collections
- **[flow validate](validate.md)** - Validate workflow syntax
- **[flow visualize](visualize.md)** - Visualize workflow dependencies
- **[flow tools](tools.md)** - Manage workflow tools
- **[flow schema](schema.md)** - Inspect workflow/job/step model schemas
- **[flow collection](collection.md)** - Install and manage workflow collections

## Project Commands

- **[project init](init.md)** - Initialize new OFX project
- **[project sync](sync.md)** - Sync project to remote storage
- **[project list](project.md)** - List and manage projects

## Secret Management

- **[secret manage](secret.md)** - Manage secrets and credentials

## Utility Commands

- **[docs](docs-serve.md)** - Display API documentation and data directories
- **[doctor](doctor.md)** - Run reliability scorecards and readiness diagnostics

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

# Run for a specific project
ofx flow run workflow-name --project my-project

# Run with durable checkpoints
ofx flow run workflow-name --durable --resume

# Validate workflow syntax
ofx flow validate workflow-name

# Visualize workflow dependencies
ofx flow visualize workflow-name
```

### Managing Collections

```bash
# Install a collection from Git
ofx flow collection add https://github.com/myorg/recon-tools.git

# List installed collections
ofx flow collection list
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
| `ofx flow init <name>` | Scaffold a workflow file with IDE schema comment |
| `ofx flow run` | Execute a workflow |
| `ofx flow list` | List available workflows from all sources |
| `ofx flow validate` | Validate workflow syntax |
| `ofx flow visualize` | Visualize workflow dependency graph |
| `ofx flow tools` | Install and manage workflow tools |
| `ofx flow schema` | Inspect workflow/job/step model schemas |
| `ofx flow collection` | Manage workflow collections |
| `ofx project init` | Initialize new project |
| `ofx project sync` | Sync project to storage |
| `ofx secret manage` | Manage secrets |
| `ofx docs` | Display API documentation and data directories |
| `ofx docs --list` | List all available API modules |
| `ofx docs --module <name>` | View specific module documentation |
| `ofx doctor fleet` | Score fleet/cloud reliability readiness |
