# Cloud Runners

Cloud runners let OFX provision infrastructure, execute jobs remotely, and clean up automatically. Any job with a `cloud` field runs on a remote VPS instead of locally.

## Supported Providers

| Provider | Description | Requires |
|----------|-------------|----------|
| `digitalocean` | DigitalOcean Droplets | `DIGITALOCEAN_TOKEN` env var or token in profile |
| `aws` | Amazon EC2 instances | AWS credentials (`~/.aws/credentials` or env vars) |
| `static` | Pre-existing hosts (no provisioning) | SSH access to the host |

Install cloud extras:

```bash
pip install "ofx[cloud]"
```

## Runner Lifecycle

1. **Provision** — Create instance (or connect for static provider)
2. **Wait** — Poll for SSH/WinRM readiness
3. **Execute** — Run workflow steps remotely via SSH or WinRM
4. **Collect** — Download outputs and logs
5. **Destroy** — Terminate instance (if `auto_destroy: true`, the default)

## Setting Up Authentication

### DigitalOcean

```bash
# Set token
export DIGITALOCEAN_TOKEN=dop_v1_xxxxx

# Or include in profile
ofx cloud profile add do-small \
  --provider digitalocean \
  --region nyc1 \
  --size s-1vcpu-1gb \
  --image ubuntu-24-04-x64 \
  --ssh-user root \
  --ssh-key ~/.ssh/id_rsa
```

### AWS

```bash
# Standard AWS credential chain
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1

# Or use ~/.aws/credentials profile
ofx cloud profile add aws-east \
  --provider aws \
  --region us-east-1 \
  --size t3.medium \
  --image ami-xxxxxxxx \
  --ssh-user ubuntu \
  --ssh-key ~/.ssh/aws-key.pem
```

### Static (Pre-Existing Hosts)

```bash
ofx cloud profile add my-vps \
  --provider static \
  --ssh-user root \
  --ssh-key ~/.ssh/id_rsa \
  --host 203.0.113.10
```

## Using Profiles in Workflows

Reference a profile by name:

```yaml
jobs:
  recon:
    cloud: do-small
    steps:
      - run: nmap -sV {{ inputs.target }} -oN {{ ctx.output_path }}/scan.txt
```

## Inline Cloud Config

Define cloud settings directly in the workflow:

```yaml
jobs:
  recon:
    cloud:
      provider: aws
      region: us-east-1
      size: t3.medium
      image: ami-xxxxxxxx
      ssh_user: ubuntu
      ssh_key: ~/.ssh/aws-key.pem
      auto_destroy: true
    steps:
      - run: whoami
```

## Multi-Cloud Workflows

Different jobs can target different providers and regions:

```yaml
jobs:
  us-scan:
    cloud: aws-east
    steps:
      - run: nmap -sV {{ inputs.target }}

  eu-scan:
    cloud: do-amsterdam
    steps:
      - run: nmap -sV {{ inputs.target }}

  analyze:
    needs: [us-scan, eu-scan]    # Runs locally
    steps:
      - run: python merge_results.py
```

## Instance Lifecycle Control

| Field | Default | Description |
|-------|---------|-------------|
| `auto_destroy` | `true` | Destroy instance after job completes |
| `opsec` | `false` | Disable command echoing for stealth |
| `startup_script` | `""` | User data / cloud-init script |

!!! warning "Cost Control"
    When `auto_destroy: false`, instances remain running after the workflow completes. Always verify instances are terminated to avoid unexpected charges. Use `ofx cloud instance list` to check.

!!! tip "Pre-Baked Images"
    For frequently used tool stacks, create a snapshot with tools pre-installed. This speeds up execution and avoids installing tools on every run. Use `ofx cloud image` commands to manage snapshots.

## Fleet + Matrix

Use `strategy.fleet` and/or `strategy.matrix` to distribute target sets and parameter combinations across instances.

See detailed pages:

- [Cloud Configuration](cloud/configuration.md)
- [Fleet Strategy](cloud/fleet.md)
- [Cloud Lifecycle](cloud/lifecycle.md)
- [Cloud Variables](cloud/variables.md)
- [Detached Sessions](cloud-sessions.md)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| SSH connection timeout | Check security group/firewall allows port 22; verify SSH key is correct |
| Instance fails to provision | Verify API token/credentials; check quota limits |
| Tools missing on remote host | Add a `tools:` block or use a pre-baked image |
| Output files not collected | Ensure files are under `{{ ctx.output_path }}` |
