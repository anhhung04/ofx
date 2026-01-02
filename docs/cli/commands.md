# CLI Commands Reference

OFX provides a comprehensive command-line interface for workflow execution, project management, API exploration, and documentation.

## Quick Reference

| Command | Subcommands | Purpose |
|---------|-------------|---------|
| **flow** (x, task) | run, validate, update, tools | Execute and manage workflows |
| **project** | init, sync, list, remove | Manage Red Team projects |
| **secret** | set, get, list, search, delete, export, import, backup, restore, history, clear, store, migrate | Manage encrypted secrets |
| **dump** | schema, flow | Display workflow schemas and configurations |
| **docs** | serve, api | Access documentation and API reference |
| **asset** | init | Initialize OFX assets |
| **doctor** | check, install-help, path | System health and diagnostics |

## Command Structure

```bash
ofx <command> <subcommand> [options] [arguments]
```

## Global Options

All commands support these global options:

- `--help, -h` - Show help message and command documentation
- `--version` - Display OFX version information

---

## flow / x / task

**Manage and run workflows in the OFX system**

Aliases: `x`, `task` - You can use `ofx x run` or `ofx task run` instead of `ofx flow run`

### flow run

Execute a workflow with optional inputs and outputs.

```bash
ofx flow run <workflow_name> [options]
ofx x run <workflow_name> [options]          # Using alias
```

**Arguments:**
- `workflow_name` (required) - Name of the workflow to run

**Options:**
- `-i, --input <key=value>` - Input parameters (can be specified multiple times)
- `-o, --output <path>` - Output directory for results (default: current directory)

**Examples:**

```bash
# Run a simple workflow
ofx flow run port_scan

# Run with inputs
ofx flow run subdomain_enum --input domain=example.com

# Run with multiple inputs
ofx flow run api_scan \
  --input target=https://api.example.com \
  --input endpoints=/users,/admin,/api

# Specify output directory
ofx flow run comprehensive_scan \
  --input target=10.0.0.1 \
  --output ./results/scan-2024-12-25
```

### flow validate

Validate workflow configuration syntax and structure.

```bash
ofx flow validate <workflow_name>
```

**Arguments:**
- `workflow_name` (required) - Name of the workflow to validate

**Examples:**

```bash
# Validate a workflow before running
ofx flow validate my_workflow

# Check for errors in workflow definition
ofx flow validate complex_multi_stage_assessment
```

### flow update

Update workflow configuration and dependencies.

```bash
ofx flow update
```

**Examples:**

```bash
# Update all workflows
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

**Examples:**

```bash
# Install tools for specific workflow
ofx flow tools web_scanner

# Install tools from all workflows
ofx flow tools --all
```

---

## project

**Manage Red Team projects**

Project management including initialization, synchronization, and remote storage.

### project init

Initialize a new Red Team project with optional remote storage and encryption.

```bash
ofx project init <name> [options]
```

**Arguments:**
- `name` (required) - Project name

**Options:**
- `-m, --multiphase` - Initialize a multi-phase project

**Interactive Setup:**
The command will interactively prompt for:
- Remote storage type (git, ssh, s3, webdav, none)
- Repository/server details
- Encryption options

**Examples:**

```bash
# Initialize simple project
ofx project init my_engagement

# Initialize multi-phase project
ofx project init enterprise_assessment --multiphase

# Project with Git remote
ofx project init client_pentest
# Then follow prompts for Git URL and encryption
```

### project sync

Synchronize project with remote storage.

```bash
ofx project sync [options]
```

**Options:**
- `--push` - Push local changes to remote
- `--pull` - Pull remote changes to local
- `--force` - Force sync operation

**Examples:**

```bash
# Sync with remote
ofx project sync

# Force push changes
ofx project sync --push --force

# Pull latest from remote
ofx project sync --pull
```

### project list

List all available projects.

```bash
ofx project list
```

**Description:**
Shows all projects in the default project path with their details and status.

**Output:**
- Project names
- Creation dates
- Current active project (marked)

**Examples:**

```bash
# List all projects
ofx project list
```

### project remove

Remove a project by name.

```bash
ofx project remove <name> [options]
```

**Arguments:**
- `name` (required) - Project name to remove

**Options:**
- `-f, --force` - Skip confirmation prompt

**Description:**
Permanently deletes a project and all its data. Use with caution.

**Examples:**

```bash
# Remove project with confirmation
ofx project remove old_engagement

# Remove without confirmation
ofx project remove test_project --force
```

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
- `-v, --value <value>` - Secret value (if not provided, will prompt securely)
- `-f, --file <path>` - Read secret value from file

**Examples:**

```bash
# Set secret interactively (hidden input)
ofx secret set API_KEY

# Set secret directly
ofx secret set DATABASE_URL --value "postgresql://user:pass@host/db"

# Set secret from file
ofx secret set SSH_PRIVATE_KEY --file ~/.ssh/id_rsa

# Set JSON secret
ofx secret set AWS_CREDENTIALS --value '{"access_key":"xxx","secret_key":"yyy"}'
```

### secret get

Retrieve a secret value.

```bash
ofx secret get <name> [options]
```

**Arguments:**
- `name` (required) - Secret name

**Options:**
- `-s, --show` - Display the secret value (otherwise just confirms existence)

**Examples:**

```bash
# Check if secret exists
ofx secret get API_KEY

# Show secret value
ofx secret get API_KEY --show

# Show JSON secret formatted
ofx secret get AWS_CREDENTIALS --show
```

### secret list

List all stored secrets with optional filtering and searching.

```bash
ofx secret list [options]
```

**Options:**
- `-f, --filter <type>` - Filter by type (string, json, api-key, password, token)
- `-s, --search <pattern>` - Search in secret names (case-insensitive)
- `--show-values` - Show secret values (WARNING: displays sensitive data)

**Output:**
- Secret names
- Value types (string, json, api-key, password, token)

**Examples:**

```bash
# List all secrets
ofx secret list

# Filter by type
ofx secret list --filter json
ofx secret list --filter password

# Search by name pattern
ofx secret list --search api
ofx secret list --search "*token*"

# Show values (use with caution)
ofx secret list --show-values
```

### secret search

Search for secrets by name pattern with wildcard support.

```bash
ofx secret search <pattern> [options]
```

**Arguments:**
- `pattern` (required) - Search pattern (supports wildcards: `*` and `?`)

**Options:**
- `--show-values` - Show secret values (WARNING: displays sensitive data)

**Description:**
Performs pattern matching on secret names using wildcards. `*` matches any sequence of characters, `?` matches any single character.

**Examples:**

```bash
# Search for all secrets containing "api"
ofx secret search "*api*"

# Search for secrets starting with "aws"
ofx secret search "aws*"

# Search for exact match
ofx secret search "github_token"

# Show values for matching secrets
ofx secret search "*key*" --show-values
```

### secret delete

Delete a secret from storage.

```bash
ofx secret delete <name> [options]
```

**Arguments:**
- `name` (required) - Secret name to delete

**Options:**
- `-f, --force` - Skip confirmation prompt

**Examples:**

```bash
# Delete with confirmation
ofx secret delete OLD_API_KEY

# Delete without confirmation
ofx secret delete TEMP_TOKEN --force
```

### secret export

Export secrets to a file for backup or migration.

```bash
ofx secret export [options]
```

**Options:**
- `-o, --output <path>` - Output file path (default: secrets_backup.json)
- `--plain` - Export without encryption (not recommended)

**Description:**
Creates an encrypted backup of all secrets. Keep the backup file secure.

**Examples:**

```bash
# Export to default file
ofx secret export

# Export to specific file
ofx secret export --output /secure/backup.json
```

### secret import

Import secrets from a backup file.

```bash
ofx secret import <file> [options]
```

**Arguments:**
- `file` (required) - Path to secrets backup file

**Options:**
- `--merge` - Merge with existing secrets (default: replace)
- `-f, --force` - Skip confirmation for overwrites

**Description:**
Restores secrets from a backup file. By default, replaces all existing secrets.

**Examples:**

```bash
# Import and replace all secrets
ofx secret import secrets_backup.json

# Import and merge with existing
ofx secret import secrets_backup.json --merge

# Import without confirmation
ofx secret import secrets_backup.json --force
```

### secret backup

Create an encrypted backup of all secrets with timestamp.

```bash
ofx secret backup [options]
```

**Options:**
- `-o, --output <path>` - Output file path (default: auto-generated with timestamp)
- `--plain` - Export without encryption (not recommended)

**Description:**
Creates a timestamped, encrypted backup of all secrets. The backup includes metadata like creation time and can be restored later. Backups are stored in the OFX secrets directory by default.

**Examples:**

```bash
# Create backup with auto-generated name
ofx secret backup

# Create backup with custom name
ofx secret backup --output my_backup.json

# Create unencrypted backup (not recommended)
ofx secret backup --plain --output plain_backup.json
```

### secret restore

Restore secrets from a backup file with conflict resolution.

```bash
ofx secret restore <file> [options]
```

**Arguments:**
- `file` (required) - Path to backup file

**Options:**
- `--strategy <mode>` - Conflict resolution strategy (skip, overwrite, rename)
- `-f, --force` - Skip confirmation prompts

**Description:**
Restores secrets from a backup file. Supports different conflict resolution strategies when secrets already exist.

**Examples:**

```bash
# Restore with default strategy (overwrite)
ofx secret restore backup_20241227_143022.json

# Skip existing secrets
ofx secret restore backup.json --strategy skip

# Rename conflicting secrets
ofx secret restore backup.json --strategy rename

# Force restore without confirmation
ofx secret restore backup.json --force
```

### secret history

View backup history and manage backup files.

```bash
ofx secret history [options]
```

**Options:**
- `--clean` - Remove old backup files (keep last 10)
- `--list` - Show detailed backup information

**Description:**
Displays information about existing backups, including creation time, size, and status. Can also clean up old backups.

**Examples:**

```bash
# Show backup history
ofx secret history

# Show detailed backup info
ofx secret history --list

# Clean old backups
ofx secret history --clean
```

### secret clear

Clear all secrets from storage.

```bash
ofx secret clear [options]
```

**Options:**
- `-f, --force` - Skip confirmation prompt

**Description:**
Removes ALL secrets from encrypted storage. This action cannot be undone.

**Examples:**

```bash
# Clear all secrets with confirmation
ofx secret clear

# Clear without confirmation
ofx secret clear --force
```

### secret store

Display the path to the secret store file.

```bash
ofx secret store
```

**Description:**
Shows the location of the encrypted secrets file for backup or inspection.

**Examples:**

```bash
# Show secret store location
ofx secret store
```

### secret migrate

Migrate secrets between different storage formats or locations.

```bash
ofx secret migrate [options]
```

**Options:**
- `--from <format>` - Source format (v1, v2, plain)
- `--to <format>` - Target format (v2, v3)

**Description:**
Upgrades secret storage format when OFX versions change.

**Examples:**

```bash
# Migrate to latest format
ofx secret migrate --from v1 --to v2
```

---

## dump

**Dump workflow configuration and outputs**

Display workflow schema, properties, and data models for reference.

### dump schema

Display workflow schema information in formatted tables.

```bash
ofx dump schema [options]
```

**Options:**
- `--workflow` - Show workflow-level properties only
- `--job` - Show job-level properties only
- `--step` - Show step-level properties only
- `--json` - Output in JSON format

**Description:**
Displays the complete workflow data model including all properties,
types, defaults, and descriptions for workflow, job, and step objects.

**Examples:**

```bash
# Dump complete schema (all levels)
ofx dump schema

# Show only workflow properties
ofx dump schema --workflow

# Show job properties
ofx dump schema --job

# Export schema as JSON
ofx dump schema --json > workflow_schema.json
```

### dump flow

Dump a specific workflow's configuration.

```bash
ofx dump flow <workflow_name> [options]
```

**Arguments:**
- `workflow_name` (required) - Name of the workflow to dump

**Options:**
- `--json` - Output in JSON format
- `--yaml` - Output in YAML format (default)

**Description:**
Shows the complete configuration of a workflow including all jobs,
steps, hooks, inputs, and secrets.

**Examples:**

```bash
# Dump workflow configuration
ofx dump flow port_scan

# Dump as JSON
ofx dump flow port_scan --json

# Save to file
ofx dump flow my_workflow --yaml > workflow_backup.yml
```

---

## docs

**Documentation server and API reference**

Access OFX documentation and explore API functions.

### docs serve

Serve documentation locally using HTTP server.

```bash
ofx docs serve [options]
```

**Options:**
- `-h, --host <address>` - Host to bind to (default: 127.0.0.1)
- `-p, --port <number>` - Port to bind to (default: 8000)

**Examples:**

```bash
# Serve on default port 8000
ofx docs serve

# Serve on custom port
ofx docs serve --port 8080

# Serve on all interfaces
ofx docs serve --host 0.0.0.0 --port 80
```

**Access:** Open http://127.0.0.1:8000 in your browser

### docs api

Display OFX API documentation in terminal.

```bash
ofx docs api [options]
```

**Options:**
- `-l, --list` - List all available API modules
- `-m, --module <name>` - View specific module documentation
- `-f, --function <name>` - View specific function/class details

**Examples:**

```bash
# List all API modules
ofx docs api --list

# View module documentation
ofx docs api --module webshell

# View specific function
ofx docs api --module http --function send_request

# View class method
ofx docs api --module webshell --function WebShell.execute
```

**Output Format:**
- Function signatures with type hints
- Parameter tables (name, type, required, default)
- Return types
- Docstrings and examples
- Model schemas for complex types

---

## asset

**Manage OFX assets**

Asset initialization and management.

### asset init

Initialize new OFX assets.

```bash
ofx asset init
```

**Interactive:** Prompts for asset type and configuration.

**Examples:**

```bash
# Initialize asset
ofx asset init
```

---

## doctor

**Check system dependencies and required tools**

Verify installation and availability of essential and recommended tools.

### doctor check

Run comprehensive system health check.

```bash
ofx doctor check [options]
```

**Options:**
- `--verbose` - Show detailed diagnostic information
- `--json` - Output results in JSON format

**Description:**
Checks for all essential and recommended tools including:
- Git, curl, Python 3.10+
- uv package manager
- Go toolchain
- Node.js runtime
- Common security tools (nmap, masscan, nuclei, etc.)

**Examples:**

```bash
# Run basic health check
ofx doctor check

# Run with detailed output
ofx doctor check --verbose

# Export results as JSON
ofx doctor check --json > system_status.json
```

**Output:**
- ✓ Green checks for installed tools with versions
- ✗ Red warnings for missing tools
- Installation suggestions and links

### doctor install-help

Show installation instructions for tools.

```bash
ofx doctor install-help [tool_name]
```

**Arguments:**
- `tool_name` (optional) - Specific tool to show help for

**Description:**
Displays detailed installation instructions for missing or specified tools.

**Examples:**

```bash
# Show help for all missing tools
ofx doctor install-help

# Show help for specific tool
ofx doctor install-help nmap
ofx doctor install-help golang
```

**Output:**
- Installation commands for current OS
- Package manager recommendations
- Download links and documentation

### doctor path

Show PATH environment variable directories.

```bash
ofx doctor path
```

**Description:**
Displays all directories in your PATH environment variable to help
diagnose tool discovery issues.

**Examples:**

```bash
# Show PATH directories
ofx doctor path
```

**Output:**
- List of all PATH directories
- Indicates which ones exist vs missing
- Shows tool locations in each directory

```bash
ofx doctor [options]
```

**Options:**
- `--fix` - Attempt to fix issues automatically
- `--verbose` - Show detailed diagnostic information

**Examples:**

```bash
# Run health check
ofx doctor

# Run with fix suggestions
ofx doctor --fix
```

**Checks:**
- Git installation and version
- curl availability
- Python 3.10+ runtime
- uv package manager
- Go toolchain
- Node.js runtime
- Common security tools (nmap, masscan, nuclei, etc.)

**Output:**
- ✓ Green checks for installed tools
- ✗ Red warnings for missing tools
- Installation suggestions and links

---

## Common Workflows

### Initial Setup

```bash
# Check system dependencies
ofx doctor

# Initialize a project
ofx project init my_first_project

# Set up secrets
ofx secret set SHODAN_API_KEY
ofx secret set GITHUB_TOKEN

# Validate workflow
ofx flow validate recon

# Run workflow
ofx flow run recon --input target=example.com
```

### Daily Operations

```bash
# Switch project
ofx project switch client_engagement

# Pull latest workflows
ofx flow update

# Install required tools
ofx flow tools --all

# Run assessment
ofx x run comprehensive_scan \
  --input target=10.0.0.0/24 \
  --output ./results/$(date +%Y%m%d)

# Check results
ls -lah ./results/$(date +%Y%m%d)/
```

### Development & Testing

```bash
# Validate workflow changes
ofx flow validate custom_workflow

# Check API documentation
ofx docs api --list
ofx docs api --module http

# View local docs
ofx docs serve --port 8000

# Dump schema for reference
ofx dump schema --workflow > workflow_schema.txt
```

### Secret Management

```bash
# Set multiple secrets interactively
ofx secret set SHODAN_API_KEY
ofx secret set GITHUB_TOKEN
ofx secret set NESSUS_ACCESS_KEY
ofx secret set NESSUS_SECRET_KEY

# Import from file
ofx secret set AWS_CONFIG --file ~/.aws/credentials

# List all secrets
ofx secret list

# Verify secret exists
ofx secret get SHODAN_API_KEY

# Export backup
ofx secret export --output ~/backups/secrets_$(date +%Y%m%d).json

# Clean up old secrets
ofx secret delete OLD_KEY --force

# Clear all and start fresh
ofx secret clear --force
```

### Project Management Workflow

```bash
# Initialize new engagement
ofx project init client_pentest_2025

# Set up Git sync with encryption
# (Interactive prompts will ask for Git URL and encryption key)

# Work on project
ofx flow run recon --input target=client.com

# Sync to remote
ofx project sync --push

# Switch to different project
ofx project list
ofx project switch previous_engagement

# Pull latest from remote
ofx project sync --pull

# Archive old project
ofx project remove old_engagement
```

### Workflow Development Cycle

```bash
# 1. Create/edit workflow file
vim ~/.config/ofx/workflows/custom_scan.yml

# 2. Validate syntax
ofx flow validate custom_scan

# 3. Check schema for available properties
ofx dump schema --job
ofx dump schema --step

# 4. Install required tools
ofx flow tools custom_scan

# 5. Test run
ofx x run custom_scan --input target=test.local

# 6. View API docs for enhancements
ofx docs api --list
ofx docs api --module http

# 7. Update and re-validate
ofx flow validate custom_scan

# 8. Production run
ofx flow run custom_scan \
  --input target=production.com \
  --output ./results/prod-scan-$(date +%Y%m%d_%H%M%S)
```

### Troubleshooting Workflow

```bash
# Check system health
ofx doctor check --verbose

# Show PATH for tool discovery issues
ofx doctor path

# Get installation help for missing tool
ofx doctor install-help nmap

# Verify workflow configuration
ofx dump flow my_workflow --yaml

# Check secret store location
ofx secret store

# List available workflows
ls -lah ~/.config/ofx/workflows/

# View workflow with all resolved values
ofx dump flow recon --json | jq .
```

### Multi-Environment Operations

```bash
# Development environment
export OFX_CONFIG_DIR=~/projects/dev/.ofx
ofx flow run test_workflow

# Staging environment  
export OFX_CONFIG_DIR=~/projects/staging/.ofx
ofx secret import staging_secrets.json
ofx flow run integration_tests

# Production environment
export OFX_CONFIG_DIR=~/projects/prod/.ofx
ofx project sync --pull
ofx flow run production_scan \
  --input target=production.example.com \
  --output ./results/prod/$(date +%Y%m%d)
```

---

## Environment Variables

OFX respects these environment variables:

- `OFX_CONFIG_DIR` - Override default config directory (~/.config/ofx)
- `OFX_DATA_DIR` - Override default data directory (~/.local/share/ofx)
- `OFX_WORKFLOW_DIRS` - Additional workflow directories (colon-separated)
- `OFX_SECRETS_FILE` - Custom secrets file location
- `OFX_LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)

**Example:**

```bash
export OFX_CONFIG_DIR=/opt/ofx/config
export OFX_LOG_LEVEL=DEBUG
ofx flow run my_workflow
```

---

## Tips & Tricks

### Using Aliases

Flow command has convenient aliases for faster typing:

```bash
ofx x run scan           # Instead of: ofx flow run scan
ofx task run enum        # Instead of: ofx flow run enum
```

### Command Chaining

Combine commands for complex workflows:

```bash
# Validate, install tools, then run
ofx flow validate scan && \
ofx flow tools scan && \
ofx x run scan --input target=example.com

# Run and backup results
ofx flow run assessment --output ./results && \
tar -czf results_$(date +%Y%m%d).tar.gz results/

# Export secrets before system migration
ofx secret export --output backup.json && \
ofx project sync --push
```

### Output Redirection

Capture command output for processing:

```bash
# Save workflow schema
ofx dump schema --json > schema.json

# Save workflow configuration
ofx dump flow recon --yaml > recon_backup.yml

# Export project list
ofx project list --json > projects.json

# Save secret list (names only, not values)
ofx secret list --json > secret_inventory.json
```

### Using with Other Tools

Integrate OFX with system tools:

```bash
# Run workflow and send notification
ofx flow run scan && notify-send "Scan Complete"

# Parallel workflow execution
parallel ofx flow run {} --input target=example.com ::: scan1 scan2 scan3

# Schedule workflows with cron
# Run every day at 2 AM
0 2 * * * cd /path/to/project && ofx x run daily_scan --output /results/$(date +\%Y\%m\%d)

# Monitor workflow in tmux/screen
tmux new-session -d -s ofx_scan 'ofx flow run long_scan'
```

### Configuration Management

Manage OFX configuration efficiently:

```bash
# Backup entire configuration
tar -czf ofx_backup_$(date +%Y%m%d).tar.gz ~/.config/ofx/

# Copy workflows to new system
rsync -av ~/.config/ofx/workflows/ newserver:~/.config/ofx/workflows/

# Version control workflows
cd ~/.config/ofx/workflows/
git init
git add *.yml
git commit -m "Initial workflows"

# Share workflows with team
git remote add origin https://github.com/team/ofx-workflows.git
git push -u origin main
```

---

## Exit Codes

OFX follows standard exit code conventions:

- `0` - Success
- `1` - General error
- `2` - Command syntax error
- `130` - Interrupted (Ctrl+C)

**Example in scripts:**

```bash
#!/bin/bash
if ofx flow validate my_workflow; then
    ofx flow run my_workflow --input target=$TARGET
else
    echo "Workflow validation failed"
    exit 1
fi
```

---

## Getting Help

- Run `ofx <command> --help` for detailed command help
- Visit documentation: `ofx docs serve`
- View API reference: `ofx docs api --list`
- Check system health: `ofx doctor`
