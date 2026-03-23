# Cloud Runners

Cloud runners let OFX provision infrastructure, execute jobs remotely, and optionally clean up automatically.

## Supported providers

- `digitalocean`
- `aws`
- `static` (pre-existing hosts)

## Runner lifecycle

1. Provision instance (or connect for static provider)
2. Wait for SSH/WinRM readiness
3. Execute workflow steps remotely
4. Collect outputs/logs
5. Destroy instance (if `auto_destroy: true`)

## Install cloud extras

```bash
pip install "ofx[cloud]"
```

## Create a profile

```bash
ofx cloud profile add do-small \
  --provider digitalocean \
  --region nyc1 \
  --size s-1vcpu-1gb \
  --image ubuntu-24-04-x64 \
  --ssh-user root \
  --ssh-key ~/.ssh/id_rsa
```

## Use profile in workflow

```yaml
jobs:
  recon:
    cloud: do-small
    steps:
      - run: nmap -sV {{ inputs.target }} -oN {{ ctx.output_path }}/scan.txt
```

## Inline cloud config

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

## Fleet + matrix

Use `strategy.fleet` and/or `strategy.matrix` to distribute target sets and parameter combinations across instances.

See detailed pages:

- [Cloud configuration](cloud/configuration.md)
- [Fleet strategy](cloud/fleet.md)
- [Cloud lifecycle](cloud/lifecycle.md)
- [Cloud variables](cloud/variables.md)
- [Detached sessions](cloud-sessions.md)

## Notes

- Use profile-based config for repeatable runs.
- Prefer secrets for credentials and tokens.
- Keep generated artifacts under `ctx.output_path` for reliable retrieval.
