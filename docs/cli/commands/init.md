# project init

Initialize a new OFX project with remote storage configuration.

## Usage

```bash
ofx project init [project-name]
```

## Description

The `init` command creates a new OFX project with directory structure, sample workflows, and configures remote storage for synchronization. It provides an interactive setup experience for storage backend selection.

## Arguments

- `project-name` (optional) - Name of the project (default: current directory name)

## Interactive Setup

When you run `ofx project init`, you'll be guided through:

1. **Project Name**: Enter a unique project identifier
2. **Storage Type**: Choose remote storage backend
   - `git` - Git repository (GitHub, GitLab, Bitbucket, etc.)
   - `s3` - AWS S3 or compatible object storage
   - `none` - Local-only project (no remote sync)
3. **Storage Configuration**: Provide backend-specific details
4. **Encryption**: Enable encryption for sensitive data

## Storage Backends

### Git Storage

Version-controlled storage with full commit history.

**Interactive prompts**:
- Git repository URL (e.g., `git@github.com:user/repo.git`)
- Branch name (default: `main`)
- Enable encryption? (yes/no)

**Example**:
```bash
ofx project init pentest-2024

# Interactive prompts:
# Project name: pentest-2024
# Storage type: git
# Repository URL: git@github.com:myorg/pentest-2024.git
# Branch: main
# Enable encryption: yes
```

**Creates**:
```
pentest-2024/
├── workflows/        # Workflow YAML files
├── outputs/         # Execution outputs
├── .git/           # Git repository
├── .gitattributes  # Git filters (if encryption enabled)
├── .ofx-encryption-key  # Encryption key (if enabled)
└── README.md       # Project documentation
```

### S3 Storage

Scalable cloud storage with Git bundle-based sync.

**Interactive prompts**:
- S3 bucket name
- AWS region (e.g., `us-east-1`)
- Bucket prefix/path (optional)
- Enable encryption? (yes/no)

**Prerequisites**:
AWS credentials configured via:
```bash
# Option 1: Environment variables
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="us-east-1"

# Option 2: AWS CLI
aws configure
```

**Example**:
```bash
ofx project init redteam-ops

# Interactive prompts:
# Project name: redteam-ops
# Storage type: s3
# S3 bucket: my-ofx-backups
# Region: us-east-1
# Prefix: projects/redteam
# Enable encryption: yes
```

**Creates**:
```
redteam-ops/
├── workflows/
├── outputs/
├── .git/           # Local Git repository
├── .ofx-config.yml # S3 configuration
└── README.md
```

### No Storage

Local-only project without remote synchronization.

**Example**:
```bash
ofx project init local-tests

# Interactive prompts:
# Project name: local-tests
# Storage type: none
```

## Command Line Options

While `init` is primarily interactive, you can provide some options:

```bash
# Specify project name
ofx project init my-project

# Non-interactive mode (future feature)
# ofx project init --name my-project --storage git --remote https://github.com/user/repo.git
```

## After Initialization

1. **Add Workflows**: Create YAML files in `workflows/`
   ```bash
   cd my-project/workflows
   vim recon.yml
   ```

2. **Add Secrets**: Store sensitive data
   ```bash
   ofx secret add API_KEY --value "..."
   ```

3. **Run Workflows**: Execute tasks
   ```bash
   ofx flow run recon
   ```

4. **Sync to Remote**: Backup to remote storage
   ```bash
   ofx project sync my-project
   ```

## Examples

### Penetration Test Project with Git

```bash
ofx project init pentest-client-abc
# Select: git → git@github.com:myorg/pentest-abc.git → encrypt: yes
cd pentest-client-abc
# Add workflows, execute, sync automatically
```

### Red Team Operations with S3

```bash
# Configure AWS first
aws configure

ofx project init redteam-2024
# Select: s3 → bucket: redteam-ops → region: us-east-1 → encrypt: yes
cd redteam-2024
# Work locally, manually sync when needed
```

### Quick Local Testing

```bash
ofx project init quick-test
# Select: none
cd quick-test
# No remote sync, purely local workflows
```

## Project Structure

Initialized project contains:

```
my-project/
├── workflows/           # Workflow definitions
│   └── example.yml     # Sample workflow
├── outputs/            # Execution outputs (auto-created)
├── .git/              # Git repository
├── .ofx-config.yml    # OFX project configuration
├── .gitignore         # Git ignore patterns
└── README.md          # Project documentation
```

## Configuration Files

### `.ofx-config.yml`
Stores project settings:
```yaml
name: my-project
storage:
  type: git|s3|none
  config:
    # Storage-specific configuration
encrypted: true|false
created: 2024-01-15T10:30:00Z
```

### `.ofx-encryption-key` (Git + encryption)
Contains encryption key for Git filter encryption.

**Important**: 
- Add to `.gitignore` (done automatically)
- Backup securely (lost keys = lost data)

## See Also

- [project sync](sync.md) - Sync project to remote storage
- [project list](project.md) - List all projects
- [S3 Workflows](../../guide/workflows/s3-workflows.md) - Using S3 for workflows
- [Secrets Management](../../guide/secrets-inputs.md) - Managing secrets