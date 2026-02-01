# CLI Commands Reference

OFX provides a comprehensive command-line interface for workflow execution, project management, API exploration, and documentation.

## Quick Reference

| Command | Subcommands | Purpose |
|---------|-------------|---------|
| **flow** (x, task) | run, validate, update, tools, visualize | Execute and manage workflows |
| **project** | init, sync, list, remove, import | Manage Red Team projects |
| **secret** | set, get, list, search, delete, export, import, backup, restore, history, clear, store, migrate | Manage encrypted secrets |
| **dump** | schema, flow, job, step | Display workflow schemas and configurations |
| **docs** | api | Access documentation and API reference |
| **asset** | init | Initialize OFX assets |
| **doctor** | check, install-help | System health and diagnostics |

## Command Structure

```bash
ofx <command> <subcommand> [options] [arguments]
```

## Global Options

All commands support these global options:

- `--help` - Show help message and command documentation

---

## flow / x / task

**Manage and run workflows in the OFX system**

Aliases: `x`, `task` - You can use `ofx x run` or `ofx task run` instead of `ofx flow run`

### flow run

Execute a workflow with optional inputs and outputs.

```bash
ofx flow run <workflow_name> [options]
```

**Arguments:**
- `workflow_name` (required) - Name of the workflow to run

**Options:**
- `-i, --input <key=value>` - Input parameters (can be specified multiple times)
- `-o, --output <path>` - Output directory for results (default: current directory)
- `--profile` - Enable performance profiling

### flow validate

Validate workflow configuration syntax and structure.

```bash
ofx flow validate [workflow_name]
```

**Arguments:**
- `workflow_name` (optional) - Name of the workflow to validate

### flow update

Update workflow configuration and dependencies.

```bash
ofx flow update
```

### flow tools

Install tools configured in workflow(s).

```bash
ofx flow tools [workflow_name] [options]
```

**Arguments:**
- `workflow_name` (optional) - Name of specific workflow to install tools from

**Options:**
- `-a, --all` - Install tools from all workflows

### flow visualize

Visualize workflow as a directed acyclic graph (DAG).

```bash
ofx flow visualize <workflow_name> [options]
```

**Arguments:**
- `workflow_name` (required) - Name of the workflow to visualize

**Options:**
- `-o, --output <path>` - Output path for the visualization file. If not specified, displays in terminal.
- `--format <format>` - Output format: `dot`, `png`, `svg`, `pdf` (default: `dot`)

---

## project

**Manage Red Team projects**

Project management including initialization, synchronization, and remote storage.

### project init

Initialize a new Red Team project.

```bash
ofx project init <name> [options]
```

**Arguments:**
- `name` (required) - Project name

**Options:**
- `-m, --multiphase` - Initialize a multi-phase project

### project sync

Sync local project with remote storage (git by default).

```bash
ofx project sync <project> [options]
```

**Arguments:**
- `project` (required) - Project name or path

**Options:**
- `-t, --remote-type <type>` - Remote storage type: git or ssh (default: git)
- `-c, --remote-config <json>` - Remote config as JSON
- `-e, --encrypt` - Encrypt files before syncing
- `--encryption-key <key>` - Encryption key (or set `OFX_ENCRYPTION_KEY` env var)
- `-m, --message <msg>` - Custom commit message for sync

### project import

Import project by cloning from remote git repository.

```bash
ofx project import <url> [options]
```

**Arguments:**
- `url` (required) - Git repository URL to clone

**Options:**
- `-n, --name <name>` - Custom name for the imported project

### project list

List all available projects.

```bash
ofx project list
```

### project remove

Remove a project by name.

```bash
ofx project remove <name>
```

**Arguments:**
- `name` (required) - Project name to remove

---

## secret

**Manage secrets for workflows**

Secure encrypted storage for API keys, tokens, and sensitive data.

### secret set

Store a secret value in encrypted storage.

```bash
ofx secret set <name> [options]
```

**Arguments:**
- `name` (required) - Secret name/identifier

**Options:**
- `-v, --value <value>` - Secret value (if not provided, will prompt)
- `-f, --file <path>` - Read secret value from file
- `-f, --force` - Overwrite existing secret without prompt

### secret get

Retrieve a secret value.

```bash
ofx secret get <name> [options]
```

**Arguments:**
- `name` (required) - Secret name

**Options:**
- `-s, --show` - Display the secret value (otherwise just confirms existence)

### secret list

List all stored secrets with optional filtering and searching.

```bash
ofx secret list [options]
```

**Options:**
- `-f, --filter <type>` - Filter by type (string, json, api-key, password, token)
- `-s, --search <pattern>` - Search in secret names
- `--show-values` - Show secret values (WARNING: displays sensitive data)

### secret search

Search for secrets by name pattern with wildcard support.

```bash
ofx secret search <pattern> [options]
```

**Arguments:**
- `pattern` (required) - Search pattern (supports wildcards: `*` and `?`)

**Options:**
- `--show-values` - Show secret values (WARNING: displays sensitive data)

### secret delete

Delete a secret from storage.

```bash
ofx secret delete <name> [options]
```

**Arguments:**
- `name` (required) - Secret name to delete

**Options:**
- `-f, --force` - Skip confirmation prompt
- `--backup-to <path>` - Create an encrypted backup before deletion
- `--backup-overwrite` - Overwrite backup file if it exists

### secret export

Export secrets to a file.

```bash
ofx secret export [options]
```

**Options:**
- `-o, --output <path>` - Output file path (default: secrets_export.json)
- `--backup-to <path>` - Create an encrypted backup before export
- `--backup-overwrite` - Overwrite backup file if it exists

**Warning:** Exports unencrypted secrets. Use `backup` for secure backups.

### secret import

Import secrets from a JSON file.

```bash
ofx secret import <file> [options]
```

**Arguments:**
- `file` (required) - Path to JSON file containing secrets

**Options:**
- `--overwrite` - Overwrite existing secrets
- `--backup-to <path>` - Create an encrypted backup before import
- `--backup-overwrite` - Overwrite backup file if it exists

### secret backup

Create an encrypted backup of all secrets.

```bash
ofx secret backup [options]
```

**Options:**
- `-o, --output <path>` - Output file path (default: auto-generated with timestamp)
- `-f, --force` - Overwrite existing backup file
- `--backup-to <path>` - Create an encrypted backup of current store before writing new backup
- `--backup-overwrite` - Overwrite pre-backup file if it exists
- `-p, --passphrase <pass>` - Passphrase to unlock the secret store
- `--ask-passphrase` - Prompt for passphrase interactively

### secret restore

Restore secrets from an encrypted backup file.

```bash
ofx secret restore <backup_file> [options]
```

**Arguments:**
- `backup_file` (required) - Path to backup file to restore from

**Options:**
- `--overwrite` - Overwrite existing secrets with same names
- `--dry-run` - Show what would be restored without actually doing it
- `--backup-to <path>` - Create an encrypted backup of current store before restoring
- `--backup-overwrite` - Overwrite pre-backup file if it exists
- `-p, --passphrase <pass>` - Passphrase to unlock the secret store
- `--ask-passphrase` - Prompt for passphrase interactively

### secret history

Show available backup files and their information.

```bash
ofx secret history [options]
```

**Options:**
- `-d, --directory <path>` - Directory to scan for backups (default: current directory)

### secret clear

Clear all secrets from storage.

```bash
ofx secret clear [options]
```

**Options:**
- `-f, --force` - Skip confirmation
- `--backup-to <path>` - Create an encrypted backup before clearing
- `--backup-overwrite` - Overwrite backup file if it exists

### secret store

Display the path to the secret store file.

```bash
ofx secret store
```

### secret migrate

Migrate secrets from legacy file-based storage to encrypted store.

```bash
ofx secret migrate [options]
```

**Options:**
- `-f, --force` - Skip confirmation

---

## dump

**Dump workflow configuration and outputs**

Display workflow schema, properties, and data models for reference.

### dump schema

Export the OFX workflow model schema as a JSON file.

```bash
ofx dump schema [options]
```

**Options:**
- `-o, --output <path>` - Output file path for the JSON schema (default: `workflow_schema.json` in data dir)

### dump flow

Display the OFX workflow model schema as a rich, human-readable tree.

```bash
ofx dump flow
```

### dump job

Display the OFX job model schema as a rich, human-readable tree.

```bash
ofx dump job
```

### dump step

Display the OFX step model schema as a rich, human-readable tree.

```bash
ofx dump step
```

---

## docs

**Documentation and API reference**

### docs api

Display OFX API documentation in terminal.

```bash
ofx docs api [options]
```

**Options:**
- `-l, --list` - List all available API modules
- `-m, --module <name>` - View specific module documentation
- `-f, --function <name>` - View specific function/class details
- `--module <name>` - Optional API module name to document
- `--function <name>` - The specific function to display details for

---

## asset

**Manage OFX assets**

### asset init

Initialize new OFX assets.

```bash
ofx asset init
```

---

## doctor

**Check system dependencies and required tools**

### doctor check

Run a comprehensive check of all system dependencies and configurations for OFX.

```bash
ofx doctor check [options]
```

**Options:**
- `-v, --verbose` - Show detailed information

### doctor install-help

Provide installation instructions for required tools.

```bash
ofx doctor install-help [tool]
```

**Arguments:**
- `tool` (optional) - Show help for a specific tool
