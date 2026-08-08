# Setup Workflows

Infrastructure and environment setup for engagements.

## Workflows

### cloud-setup
Provision AWS EC2 or DigitalOcean droplets for attack infrastructure.
```bash
ofx flow run cloud-setup --input provider=aws --input region=us-east-1
```

### docker-lab
Spin up a disposable Docker Compose security lab with vulnerable targets.
```bash
ofx flow run docker-lab --input lab_name=ofx-lab --input targets=juice-shop,dvwa
```

### git-secrets-guard
Set up pre-commit hooks for secret scanning in Git repositories.
```bash
ofx flow run git-secrets-guard --input repo_path=.
```

### proxy-config
Configure proxychains, Tor, SSH tunneling, and VPN routing.
```bash
ofx flow run proxy-config --input mode=proxychains --input proxy_host=127.0.0.1 --input proxy_port=9050
```
