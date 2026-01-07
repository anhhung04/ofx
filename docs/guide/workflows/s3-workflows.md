# S3 Workflow Resolution Examples

## Overview
OFX can now load workflows directly from Amazon S3 buckets using the `s3://` URI scheme.

## Prerequisites

1. **AWS Credentials** - Configure using one of:
   ```bash
   # Environment variables
   export AWS_ACCESS_KEY_ID=your_key_id
   export AWS_SECRET_ACCESS_KEY=your_secret_key
   export AWS_DEFAULT_REGION=us-east-1  # optional
   
   # Or use ~/.aws/credentials file
   aws configure
   ```

2. **S3 Bucket Setup**:
   - Create an S3 bucket (e.g., `my-ofx-workflows`)
   - Upload workflow YAML files
   - Ensure read permissions are granted

## Usage Examples

### Basic S3 Workflow

```bash
# Run workflow from S3 with full path
ofx flow run s3://my-workflows/security-scan.yml --input target=example.com

# Auto-detect extension (.yml or .yaml)
ofx flow run s3://my-workflows/workflows/scan --input target=10.0.0.1

# Workflow in subdirectory
ofx flow run s3://company-workflows/prod/pentest/recon.yml
```

### With Nested Workflows

If your workflow uses `uses:` to reference other workflows, they can also be on S3:

```yaml
# s3://my-workflows/main.yml
name: Main Workflow
jobs:
  recon:
    steps:
      - uses: s3://my-workflows/modules/recon.yml
        run_with:
          target: ${{ inputs.target }}
  
  exploit:
    needs: [recon]
    steps:
      - uses: s3://my-workflows/modules/exploit.yml
```

### Validation

```bash
# Validate S3 workflow before running
ofx flow validate s3://my-workflows/scan.yml

# Visualize workflow DAG
ofx flow visualize s3://my-workflows/scan.yml --format mermaid
```

## Example Workflow for S3

Upload this to your S3 bucket:

```yaml
# s3://my-workflows/example.yml
name: S3 Example Workflow
description: Simple workflow demonstrating S3 hosting

workflow_dispatch:
  inputs:
    target:
      required: true
      type: string
      description: Target host or IP

jobs:
  info:
    steps:
      - name: Show environment
        run: |
          echo "Running from S3!"
          echo "Target: ${{ inputs.target }}"
          echo "Workflow: ${{ self.name }}"
  
  scan:
    needs: [info]
    steps:
      - name: Basic scan
        run: nmap -sn ${{ inputs.target }}
```

Upload to S3:
```bash
aws s3 cp example.yml s3://my-workflows/example.yml
```

Run it:
```bash
ofx flow run s3://my-workflows/example.yml --input target=192.168.1.0/24
```

## Error Handling

### Bucket Not Found
```bash
$ ofx flow run s3://nonexistent-bucket/workflow.yml
Error: S3 bucket not found: nonexistent-bucket
```

### File Not Found
```bash
$ ofx flow run s3://my-bucket/missing.yml
Error: Workflow not found: s3://my-bucket/missing.yml
```

### Access Denied
```bash
$ ofx flow run s3://private-bucket/workflow.yml
Error: Access denied to S3. Check AWS credentials and bucket permissions.
```

## Best Practices

1. **Organize workflows by environment**:
   ```
   s3://workflows/
   ├── dev/
   │   ├── test.yml
   │   └── debug.yml
   ├── staging/
   │   └── integration.yml
   └── prod/
       ├── security-scan.yml
       └── compliance-check.yml
   ```

2. **Version workflows with prefixes**:
   ```
   s3://workflows/
   ├── v1/scan.yml
   ├── v2/scan.yml
   └── latest/scan.yml
   ```

3. **Use bucket policies for access control**:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {"AWS": "arn:aws:iam::ACCOUNT:user/ofx-user"},
         "Action": "s3:GetObject",
         "Resource": "arn:aws:s3:::my-workflows/*"
       }
     ]
   }
   ```

4. **Enable S3 versioning** to track workflow changes

5. **Use lifecycle policies** to archive old workflow versions

## Performance

- Downloaded workflows are cached in `/tmp/.ofx_s3_*/`
- Workflows are re-downloaded each run (no persistent cache)
- Use local workflows for frequently-run tasks
- S3 workflows ideal for:
  - Centralized workflow management
  - Team collaboration
  - CI/CD pipeline workflows
  - Compliance and auditing

## Security Considerations

1. **Never commit AWS credentials** to workflow files
2. **Use IAM roles** when running in EC2/ECS/Lambda
3. **Implement least privilege** - grant only s3:GetObject permission
4. **Enable S3 bucket logging** for audit trails
5. **Use S3 encryption** for sensitive workflows
6. **Consider signed URLs** for temporary access

## Integration with CI/CD

### GitHub Actions
```yaml
- name: Run OFX workflow from S3
  env:
    AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
    AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
  run: |
    ofx flow run s3://workflows/security-scan.yml --input target=${{ github.repository }}
```

### GitLab CI
```yaml
security_scan:
  script:
    - export AWS_ACCESS_KEY_ID=$AWS_KEY
    - export AWS_SECRET_ACCESS_KEY=$AWS_SECRET
    - ofx flow run s3://workflows/scan.yml --input target=$CI_PROJECT_URL
```

## Troubleshooting

### Check S3 access
```bash
# Test with AWS CLI
aws s3 ls s3://my-workflows/

# Download workflow manually
aws s3 cp s3://my-workflows/scan.yml /tmp/test.yml
```

### Debug mode
```bash
# Enable debug logging
export OFX_DEBUG=1
ofx flow run s3://my-workflows/scan.yml --input target=example.com
```

### Verify credentials
```bash
# Check current credentials
aws sts get-caller-identity

# Test S3 permissions
aws s3api head-object --bucket my-workflows --key scan.yml
```
