# project sync

Synchronize project to remote storage.

## Usage

```bash
ofx project sync [options]
```

## Description

The `sync` command backs up and synchronizes your OFX project to remote storage backends. Supports multiple storage providers with optional encryption.

## Options

- `--storage <type>` - Storage backend (required): `git`, `s3`, `ssh`, `webdav`
- `--remote <url>` - Remote URL or path (required)
- `--encrypt` - Encrypt data before upload
- `--encryption-key <key>` - Custom encryption key
- `--project <path>` - Project path (default: current directory)
- `--force` - Force sync even if conflicts exist

## Storage Backends

### Git

Sync to Git repository with version control.

```bash
ofx project sync \
  --storage git \
  --remote git@github.com:user/project.git
```

**Features**:
- Full version history
- Branch support
- Conflict resolution
- Automated commits

### S3

Sync to AWS S3 or compatible object storage.

```bash
ofx project sync \
  --storage s3 \
  --remote s3://my-bucket/projects/my-project \
  --encrypt
```

**Features**:
- Scalable storage
- Built-in redundancy
- Access control
- Encryption at rest

**Configuration**:
Set AWS credentials:
```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
```

### SSH

Sync to remote server via SSH/SFTP.

```bash
ofx project sync \
  --storage ssh \
  --remote user@server.com:/backups/my-project
```

**Features**:
- Secure transfer
- Compression
- Resume capability
- SSH key authentication

**Requirements**:
- SSH access to remote server
- SSH key configured

### WebDAV

Sync to WebDAV-compatible storage (Nextcloud, ownCloud, etc.).

```bash
ofx project sync \
  --storage webdav \
  --remote https://cloud.example.com/remote.php/dav/files/user/projects/
```

**Features**:
- Cloud storage integration
- Standard protocol
- Wide compatibility

**Authentication**:
Set credentials:
```bash
ofx secret add WEBDAV_USER --value username
ofx secret add WEBDAV_PASS --value password
```

## Encryption

### Default Encryption

```bash
ofx project sync --storage s3 --remote s3://bucket/project --encrypt
```

Uses project-specific encryption key stored in secret manager.

### Custom Encryption Key

```bash
ofx project sync \
  --storage ssh \
  --remote user@host:/backup \
  --encrypt \
  --encryption-key "$MY_KEY"
```

### What Gets Encrypted

When `--encrypt` is used:
- ✅ Workflow files
- ✅ Project data
- ✅ Outputs
- ✅ Configurations
- ❌ Metadata (for searching)

## Sync Process

1. **Prepare**: Collect project files
2. **Compress**: Create project bundle
3. **Encrypt** (if enabled): Encrypt bundle
4. **Upload**: Transfer to remote storage
5. **Verify**: Check upload integrity
6. **Cleanup**: Remove temporary files

## Examples

### Initial sync to Git

```bash
ofx project sync \
  --storage git \
  --remote https://github.com/user/my-project.git
```

### Encrypted S3 backup

```bash
ofx project sync \
  --storage s3 \
  --remote s3://my-backups/ofx-projects/pentest \
  --encrypt
```

### SSH with custom project path

```bash
ofx project sync \
  --storage ssh \
  --remote backup@server:/mnt/backups/ofx \
  --project /home/user/custom-project
```

### Force sync (overwrite remote)

```bash
ofx project sync \
  --storage git \
  --remote origin \
  --force
```

## Sync Status

Check last sync:

```bash
ofx project list
```

Shows sync status for each project.

## Troubleshooting

### Authentication Failed

**Git**: Check SSH keys or HTTPS credentials
```bash
ssh -T git@github.com
```

**S3**: Verify AWS credentials
```bash
aws s3 ls s3://bucket
```

**SSH**: Test SSH connection
```bash
ssh user@server
```

### Sync Conflicts

If remote has changes:
```bash
# Pull changes first
git pull  # for Git backend

# Or force overwrite
ofx project sync --force
```

## See Also

- [project init](init.md)
- [project](project.md)
