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

- `--path <path>` - Project location (default: `~/ofx-projects/<name>`)
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

- `--storage <type>` - Storage backend: `git`, `s3`, `ssh`, `webdav`
- `--encrypt` - Encrypt before upload
- `--remote <url>` - Remote URL/path

### Examples

```bash
# Sync to Git
ofx project sync --storage git --remote git@github.com:user/project.git

# Sync to S3 with encryption
ofx project sync --storage s3 --remote s3://bucket/project --encrypt

# Sync via SSH
ofx project sync --storage ssh --remote user@host:/path/to/backup
```

### Storage Backends

#### Git
Version-controlled project sync:

```bash
ofx project sync --storage git --remote https://github.com/user/repo.git
```

#### S3
AWS S3 or compatible storage:

```bash
ofx project sync --storage s3 --remote s3://my-bucket/projects/name
```

#### SSH
Remote server via SSH:

```bash
ofx project sync --storage ssh --remote user@server:/backups/project
```

#### WebDAV
WebDAV-compatible storage:

```bash
ofx project sync --storage webdav --remote https://webdav.server.com/projects
```

### Encryption

Enable encryption for sensitive data:

```bash
ofx project sync --encrypt --storage s3 --remote s3://bucket/project
```

Encryption uses project-specific keys stored securely.

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
