# CLI Commands

Complete reference for all OFX command-line interface commands.

## Workflow Commands

- **[flow init](flow-init.md)** - Scaffold a new workflow file with IDE schema support
- **[flow run](run.md)** - Execute workflows
- **[flow list](list.md)** - List available workflows from user, built-in, and collections
- **[flow validate](validate.md)** - Validate workflow syntax
- **[flow visualize](visualize.md)** - Visualize workflow dependencies
- **** - List, inspect, and run registered tasks
- **** - Manage workflow tools
- **[flow schema](schema.md)** - Inspect workflow/job/step model schemas
- **[flow collection](collection.md)** - Install and manage workflow collections

## Project Commands

- **[project init](init.md)** - Initialize new OFX project
- **[project sync](sync.md)** - Sync project to remote storage
- **[project list](project.md)** - List and manage projects

## Secret Management

- **[secret manage](secret.md)** - Manage secrets and credentials

## Session Management

- **[session submit](session.md#submit)** - Submit a workflow as a detached session (local or cloud)
- **[session list](session.md#list)** - List all sessions with optional filters
- **[session status](session.md#status)** - Check session status
- **[session logs](session.md#logs)** - View session output log
- **[session fetch](session.md#fetch)** - Fetch results from a completed session
- **[session decrypt](session.md#decrypt)** - Decrypt encrypted session results
- **[session cancel](session.md#cancel)** - Cancel a running session
- **[session destroy](session.md#destroy)** - Destroy a session and its resources
- **[session clean](session.md#clean)** - Remove old session data
- **[session guard](session.md#guard)** - Auto-cleanup for unattended environments
- **[session bundle](session.md#bundle)** - Create a run artifacts bundle

## Cloud Management

- **[cloud test](cloud.md#test)** - Test connectivity to a remote host
- **[cloud providers](cloud.md#providers)** - List available cloud providers
- **[cloud profile](cloud.md#profile-management)** - Manage cloud configuration profiles
- **[cloud instance](cloud.md#instance-management)** - Create, list, and destroy instances
- **[cloud image](cloud.md#image-snapshot-management)** - Manage snapshots and images
- **[cloud fleet](cloud.md#fleet-management)** - Distributed fleet operations

## AI Assistant

- **[ai generate](ai.md#generate)** - Generate a workflow from natural language
- **[ai analyze](ai.md#analyze)** - Analyze workflow output with AI
- **[ai chat](ai.md#chat)** - Interactive AI chat session
- **[ai skills](ai.md#skills)** - List analysis skill personas
- **[ai setup](ai.md#setup)** - Show AI configuration status

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
| `ofx flow tasks list` | List registered task wrappers |
| `ofx flow tasks info` | Inspect a task's options and output types |
| `ofx flow tasks run` | Run a single task directly from the CLI |
| `ofx flow tools` | Install and manage workflow tools |
| `ofx flow schema` | Inspect workflow/job/step model schemas |
| `ofx flow collection` | Manage workflow collections |
| `ofx project init` | Initialize new project |
| `ofx project sync` | Sync project to storage |
| `ofx secret manage` | Manage secrets |
| `ofx session submit` | Submit a detached workflow session |
| `ofx session list` | List sessions |
| `ofx session status` | Check session status |
| `ofx session fetch` | Fetch session results |
| `ofx cloud test` | Test remote host connectivity |
| `ofx cloud profile` | Manage cloud profiles |
| `ofx cloud instance` | Manage cloud instances |
| `ofx cloud image` | Manage snapshots/images |
| `ofx cloud fleet run` | Distributed fleet workflow execution |
| `ofx ai generate` | Generate workflow from natural language |
| `ofx ai analyze` | Analyze workflow output with AI |
| `ofx ai chat` | Interactive AI chat |
| `ofx docs` | Display API documentation and data directories |
| `ofx docs --list` | List all available API modules |
| `ofx docs --module <name>` | View specific module documentation |
| `ofx doctor fleet` | Score fleet/cloud reliability readiness |
