# project sync

Synchronize project to remote storage.

## Usage

```bash
ofx project sync <project> [options]
```

## Description

The `sync` command backs up and synchronizes your OFX project to remote storage backends. Supports Git and S3 storage with optional encryption.

## Arguments

- `project` (required) - Project name or path

## Options

- `-t, --remote-type <type>` - Remote storage type: `git` (default) or `s3`
- `-c, --remote-config <json>` - Remote config as JSON
- `-e, --encrypt` - Encrypt files before syncing
- `--encryption-key <key>` - Encryption key (or set `OFX_ENCRYPTION_KEY` env var)

## Storage Backends

### Git

Sync to Git repository with version control (default).

```bash
ofx project sync my-project
```

**Features**:
- Full version history
- Branch support
- Conflict resolution
- Automated commits
- Optional encryption via Git filters

**Configuration**:
During `project init`, provide:
- Git repository URL
- Branch (default: main)
- Encryption option

### S3

Sync to AWS S3 or compatible object storage.

```bash
ofx project sync my-project \
  --remote-type s3 \
  --remote-config '{"bucket":"my-bucket","region_name":"us-east-1"}'
```

**Features**:
- Scalable storage
- Built-in redundancy
- Access control
- Optional encryption
- Git bundle-based sync

**Configuration**:
Set AWS credentials:
```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="...
export AWS_DEFAULT_REGION="us-east-1"  # optional
```

Or use `~/.aws/credentials`:
```bash
aws configure
```

## Encryption

### Git Encryption

For Git storage, encryption is configured via Git filters during `project init`:

```bash
ofx project init my-project
# Select git as storage type
# Enable encryption when prompted
```

This sets up:
- `.gitattributes` with filter rules
- Encryption key in `.ofx-encryption-key`
- Automatic encrypt/decrypt on git operations

### S3 Encryption

For S3 storage, use the `--encrypt` flag:

```bash
ofx project sync my-project \
  --remote-type s3 \
  --encrypt \
  --encryption-key "$MY_KEY"
```

### What Gets Encrypted

When encryption is enabled:
- ✅ Workflow files
- ✅ Project data  
- ✅ Outputs
- ✅ Configurations
- ❌ Git metadata (commits, history)

## Sync Process

### Git Backend
1. **Commit**: Stage and commit local changes
2. **Encrypt** (if enabled): Git filter encrypts files
3. **Push**: Push to remote repository
4. **Verify**: Check push status

### S3 Backend
1. **Bundle**: Create Git bundle of repository
2. **Refs**: Export Git references
3. **Encrypt** (if enabled): Encrypt bundle
4. **Upload**: Upload to S3 bucket
5. **Verify**: Check upload integrity

## Examples

### Sync to Git (default)

```bash
ofx project sync my-project
```

### Encrypted S3 sync

```bash
ofx project sync pentest-2024 \
  --remote-type s3 \
  --remote-config '{"bucket":"my-backups","region_name":"us-east-1"}' \
  --encrypt \
  --encryption-key "$OFX_ENCRYPTION_KEY"
```

### S3 with custom prefix

```bash
ofx project sync enterprise-assessment \
  --remote-type s3 \
  --remote-config '{"bucket":"projects","prefix":"clients/acme"}'
```

## Sync Status

List all projects and their sync status:

```bash
ofx project list
```

Shows:
- Project name
- Project path
- Remote type (if configured)
- Last sync time

## Troubleshooting

### Git Authentication Failed

Check SSH keys or HTTPS credentials:
```bash
# Test GitHub SSH
ssh -T git@github.com

# Test GitLab SSH  
ssh -T git@gitlab.com

# Or use HTTPS with credentials
git config --global credential.helper store
```

### S3 Authentication Failed

Verify AWS credentials:
```bash
# Check credentials
aws sts get-caller-identity

# Test S3 access
aws s3 ls s3://your-bucket

# Set credentials if missing
aws configure
```

### S3 Bucket Not Found

Ensure bucket exists and you have permissions:
```bash
# Create bucket
aws s3 mb s3://my-ofx-projects --region us-east-1

# Set bucket policy for access
aws s3api put-bucket-policy --bucket my-ofx-projects --policy file://policy.json
```

### Git Sync Conflicts

If remote has diverged:
```bash
# Navigate to project
cd ~/.ofx/projects/my-project

# Pull and merge
git pull --rebase

# Resolve conflicts, then sync again
ofx project sync my-project
```

### Encryption Key Lost

If you lose your encryption key:
- **Git**: Key is in `.ofx-encryption-key` file
- **S3**: Key must be stored securely (no recovery)
- Without the key, encrypted data cannot be decrypted

## See Also

- [project init](init.md) - Initialize projects with storage
- [project](project.md) - Project management commands