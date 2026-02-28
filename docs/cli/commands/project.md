# project

Manage OFX projects.

## Usage

```bash
ofx project <subcommand> [options]
```

## Subcommands

### init

Initialize a new project.

```bash
ofx project init [project-name] [options]
```

### sync

Sync project to remote storage.

```bash
ofx project sync [options]
```

### list

List all projects.

```bash
ofx project list
```

## Project init

Initialize a new OFX project with workflows, configurations, and directory structure.

### Options

- `--path <path>` - Project location (default: `~/.ofx/projects/<name>`)
- `--template <template>` - Project template to use
- `--git` - Initialize Git repository

### Examples

```bash
# Initialize project in current directory
ofx project init my-project

# Initialize with template
ofx project init pentest --template red-team

# Initialize with Git
ofx project init recon --git
```

### Project Structure

```
my-project/
├── workflows/       # Workflow definitions
├── data/           # Project data
├── outputs/        # Execution outputs
├── .ofx/           # Project configuration
└── README.md
```

## Project sync

Synchronize project to remote storage backends.

### Options

- `--remote-type <type>` - Storage backend: `git` (default), `s3`
- `--remote-config <json>` - Remote configuration as JSON
- `--encrypt` - Encrypt before upload
- `--encryption-key <key>` - Custom encryption key

### Examples

```bash
# Sync to Git (default)
ofx project sync my-project

# Sync to S3 with encryption
ofx project sync my-project \
  --remote-type s3 \
  --remote-config '{"bucket":"my-backups","region_name":"us-east-1"}' \
  --encrypt

# Sync to S3 with custom prefix
ofx project sync pentest-2024 \
  --remote-type s3 \
  --remote-config '{"bucket":"projects","prefix":"clients/acme"}'
```

### Storage Backends

#### Git
Version-controlled project sync (default):

```bash
ofx project sync my-project
```

Features:
- Full version history
- Branch support  
- Conflict resolution
- Automated commits

#### S3
AWS S3 or compatible object storage:

```bash
ofx project sync my-project \
  --remote-type s3 \
  --remote-config '{"bucket":"my-ofx-backups","region_name":"us-east-1"}'
```

Features:
- Scalable cloud storage
- Built-in redundancy
- Access control
- Git bundle-based sync

### Encryption

Enable encryption for sensitive data:

```bash
ofx project sync my-project --encrypt --encryption-key "$MY_KEY"
```

Encryption options:
- **Git**: Configured via Git filters during init
- **S3**: Encrypted before S3 upload
- Keys must be stored securely (no recovery if lost)

## Project list

List all OFX projects.

```bash
ofx project list
```

Shows:
- Project names
- Locations
- Last modified
- Sync status

## See Also

- [project init](init.md)
- [project sync](sync.md)
